"""
生成集成模块（法律场景）
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from openai import OpenAI
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class GenerationIntegrationModule:
    """生成集成模块 - 负责法律场景答案生成"""

    HUMANIZED_OPENERS = {
        "strong": [
            "你这个问题很关键，我先给你可直接使用的结论。",
            "先说核心结论，再给你对应的依据和操作建议。",
            "我按结论、依据和建议三个层次给你说明，方便你直接落地。",
        ],
        "weak": [
            "这个问题我先给你保守判断，再把不确定点说清楚。",
            "先给你一个可参考的方向，同时把证据不足的地方标出来。",
            "我先告诉你当前可得结论，再说明哪些点还需要核实。",
        ],
        "insufficient": [
            "你这个问题很典型，但目前证据还不够，我先告诉你关键缺口。",
            "先说明当前为什么不能下确定结论，再给你下一步补充方向。",
            "我先把现有信息能支持到哪里讲清楚，再告诉你怎么补齐证据。",
        ],
    }
    PARAGRAPH_HINTS = (
        "先说",
        "结论",
        "依据",
        "另外",
        "同时",
        "不过",
        "但是",
        "因此",
        "所以",
        "建议",
        "如果",
        "需要注意",
        "最后",
        "总之",
        "当前",
    )
    ARTICLE_PATTERN = re.compile(r"第[0-9一二三四五六七八九十百千万〇零两]+条")

    def __init__(
        self,
        model_name: str = "kimi-k2-0711-preview",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        enable_legal_disclaimer: bool = True,
        risk_notice_level: str = "light",
        llm_dispatcher: Optional[object] = None,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_legal_disclaimer = enable_legal_disclaimer
        self.risk_notice_level = risk_notice_level
        self.llm_dispatcher = llm_dispatcher
        self._opener_cursor = {key: 0 for key in self.HUMANIZED_OPENERS}

        # 向后兼容：保留直接Kimi客户端能力，供未接入调度层的调用路径使用。
        self.client = None
        api_key = os.getenv("MOONSHOT_API_KEY")
        if api_key:
            self.client = OpenAI(api_key=api_key, base_url="https://api.moonshot.cn/v1")

        if self.llm_dispatcher is None and self.client is None:
            raise ValueError("请设置 MOONSHOT_API_KEY 环境变量，或接入 llm_dispatcher")

        logger.info("生成模块初始化完成，模型: %s, dispatcher=%s", model_name, bool(self.llm_dispatcher))

    def _create_generation_completion(self, messages, stream: bool = False, timeout: Optional[int] = None):
        if self.llm_dispatcher is not None:
            response, provider, model = self.llm_dispatcher.create_chat_completion(
                role="generation",
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=stream,
                timeout=timeout,
            )
            logger.info("生成调用通道: provider=%s model=%s stream=%s", provider, model, stream)
            return response
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=stream,
            timeout=timeout,
        )

    def _build_context(self, documents: List[Document]) -> str:
        context_parts: List[str] = []
        for doc in documents:
            content = doc.page_content.strip()
            if not content:
                continue
            level = doc.metadata.get("retrieval_level", "")
            law_name = doc.metadata.get("law_name", "")
            article_id = doc.metadata.get("article_id", "")
            prefix = []
            if level:
                prefix.append(level.upper())
            if law_name:
                prefix.append(law_name)
            if article_id:
                prefix.append(str(article_id))
            header = f"[{'|'.join(prefix)}] " if prefix else ""
            context_parts.append(f"{header}{content}")
        return "\n\n".join(context_parts)

    def _build_prompt(self, question: str, documents: List[Document], answer_mode: str = "strong") -> str:
        context = self._build_context(documents)
        disclaimer_clause = (
            "最后必须保留免责声明：本回答仅供参考，不构成法律意见，需由专业法律人士复核。"
            if self.enable_legal_disclaimer
            else "免责声明可省略。"
        )

        risk_instruction = (
            "风险提示保持轻量，聚焦可能后果与应对方向。"
            if self.risk_notice_level == "light"
            else "风险提示可适当展开，但避免绝对化判断。"
        )
        mode = (answer_mode or "strong").lower()
        if mode == "weak":
            mode_instruction = (
                "当前为低置信度模式：请在结尾明确写出“内容仅供参考，如需更权威回复建议您前往专业机构咨询”，"
                "并点明关键不确定点。"
            )
        elif mode == "insufficient":
            mode_instruction = (
                "当前为证据不足模式：结论必须写“当前检索证据不足以作出确定判断，请更加详细描述您的问题”，"
                "并给出补充信息建议，不得输出确定性结论。"
            )
        else:
            mode_instruction = "当前为正常回答模式：结论需谨慎、可执行，语气自然专业。"

        return f"""
你是面向普通用户的法律咨询专家。
请严格基于检索信息回答，不得编造法条，不要输出开发者口吻。

检索到的相关信息：
{context}

用户问题：{question}

输出要求（用户导向）：
- 先用 1 段自然语言直接回答用户问题。
- 根据语义适度分段，避免整段挤在一起；通常每段 2-4 句即可。
- 依据说明要自然融入正文，优先引用“法规名+条号”；条号不确定时不进行引用“法规名+条号”。
- 避免“命中率、召回、rerank、候选集”等技术术语，改为用户能理解的表达。
- 可适度使用承接类人性化表达，但不要过度口语化，不要影响专业性。
- 若证据不足，必须明确写“当前检索证据不足以作出确定判断”，并说明还需要补充什么信息。
- {risk_instruction}
- {mode_instruction}
- 不得给出“必然胜诉/绝对合法/绝对违法”等确定性执业结论。
- {disclaimer_clause}

请输出自然、专业、面向用户的中文回答：
"""

    def _has_disclaimer(self, text: str) -> bool:
        compact = text.replace(" ", "")
        return (
             "本回答不构成法律意见" in compact
        )

    def _ensure_disclaimer(self, text: str) -> str:
        return text

    def _pick_humanized_opener(self, answer_mode: str) -> str:
        mode = (answer_mode or "strong").lower()
        pool = self.HUMANIZED_OPENERS.get(mode) or self.HUMANIZED_OPENERS["strong"]
        if not pool:
            return ""
        idx = self._opener_cursor.get(mode, 0) % len(pool)
        self._opener_cursor[mode] = idx + 1
        return pool[idx]

    def _inject_humanized_opener(self, text: str, answer_mode: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return raw
        opener = self._pick_humanized_opener(answer_mode)
        if not opener:
            return raw
        # 若模型已自然开场，避免重复注入。
        if raw.startswith(("你这个问题", "先说", "我先", "这个问题")):
            return raw
        if opener[:8] in raw[:40]:
            return raw
        return f"{opener}\n\n{raw}"

    def _semantic_paragraph_format(self, text: str) -> str:
        raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not raw:
            return raw

        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        if not lines:
            return ""

        # 若已存在结构化列表/标题，尽量不破坏原结构，只做空行清理。
        if any(line.startswith(("- ", "* ", "1.", "2.", "3.", "#")) for line in lines):
            return "\n".join(lines)

        compact = re.sub(r"\s+", " ", " ".join(lines)).strip()
        sentences = [s.strip() for s in re.split(r"(?<=[。！？；!?;])\s*", compact) if s.strip()]
        if len(sentences) <= 2:
            return compact

        paragraphs: List[str] = []
        current: List[str] = []
        for sentence in sentences:
            if not current:
                current.append(sentence)
                continue

            current_text = "".join(current)
            should_break = (
                (len(current_text) >= 100 and len(current) >= 2)
                or any(sentence.startswith(hint) for hint in self.PARAGRAPH_HINTS)
            )
            if should_break:
                paragraphs.append("".join(current).strip())
                current = [sentence]
            else:
                current.append(sentence)

        if current:
            paragraphs.append("".join(current).strip())
        return "\n\n".join(p for p in paragraphs if p)

    def _post_process_answer(self, text: str, answer_mode: str) -> str:
        with_opener = self._inject_humanized_opener(text, answer_mode=answer_mode)
        return self._semantic_paragraph_format(with_opener)

    def _build_evidence_summary(self, documents: List[Document], limit: int = 3) -> str:
        if not documents:
            return "- 无可用检索证据。"
        lines: List[str] = []
        for doc in documents[:limit]:
            law_name = doc.metadata.get("law_name") or "未标注法规"
            article_id = doc.metadata.get("article_id") or "条文号未知"
            snippet = (doc.page_content or "").strip().replace("\n", " ")
            if len(snippet) > 120:
                snippet = f"{snippet[:120]}..."
            lines.append(f"- {law_name} / {article_id}: {snippet or '无正文片段'}")
        return "\n".join(lines)

    def _build_degraded_answer(self, documents: List[Document], error: Exception) -> str:
        answer = (
            "当前回答生成通道暂时不可用，我先把已检索到的关键信息给你，供你快速核对。\n\n"
            f"已检索证据摘要：\n{self._build_evidence_summary(documents)}\n\n"
            "建议你稍后重试一次；如果问题紧急，优先让专业法律人士结合法规原文做最终判断。"
        )
        logger.error("触发生成降级输出: %s", error)
        return self._post_process_answer(self._ensure_disclaimer(answer), answer_mode="weak")

    def _build_insufficient_answer(self, question: str, documents: List[Document]) -> str:
        answer = (
            f"就你问的“{question}”，当前检索证据不足以作出确定判断。\n\n"
            f"目前可供参考的检索信息如下：\n{self._build_evidence_summary(documents)}\n\n"
            "要把结论做实，建议补充更具体的事实要点（时间、行为、主体身份、是否有书面材料等），"
            "或直接给出你关心的法规名/条号，我可以据此继续精确检索并给出更稳妥的分析。\n\n"
            "在证据不充分时直接依据当前结果决策，可能导致判断偏差，建议让专业法律人士复核。"
        )
        return self._post_process_answer(self._ensure_disclaimer(answer), answer_mode="insufficient")

    def _extract_article_candidates(self, question: str, documents: List[Document]) -> List[str]:
        found: List[str] = []
        seen = set()

        for item in self.ARTICLE_PATTERN.findall(question or ""):
            if item not in seen:
                seen.add(item)
                found.append(item)

        for doc in documents or []:
            md = doc.metadata or {}
            for item in md.get("article_candidates", []) or []:
                value = str(item or "").strip()
                if value and value not in seen:
                    seen.add(value)
                    found.append(value)
        return found

    def _extract_law_candidates(self, question: str, documents: List[Document]) -> List[str]:
        found: List[str] = []
        seen = set()

        quoted = re.findall(r"《([^》]{2,40})》", question or "")
        for item in quoted:
            value = str(item or "").strip()
            if value and value not in seen:
                seen.add(value)
                found.append(value)

        for item in re.findall(r"[一-龥]{2,30}(?:法|法典|条例|规定|办法|解释)", question or ""):
            value = str(item or "").strip()
            if value and value not in seen:
                seen.add(value)
                found.append(value)

        for doc in documents or []:
            md = doc.metadata or {}
            for item in md.get("law_candidates", []) or []:
                value = str(item or "").strip()
                if value and value not in seen:
                    seen.add(value)
                    found.append(value)
        return found

    def _extract_must_terms(self, documents: List[Document]) -> List[str]:
        terms: List[str] = []
        seen = set()
        for doc in documents or []:
            md = doc.metadata or {}
            for item in md.get("must_terms", []) or []:
                value = str(item or "").strip().lower()
                if not value or value in seen:
                    continue
                seen.add(value)
                terms.append(value)
        return terms

    def _is_article_intent(self, question: str, documents: List[Document], article_candidates: List[str]) -> bool:
        if self.ARTICLE_PATTERN.search(question or ""):
            return True
        if article_candidates:
            return True
        for doc in documents or []:
            if (doc.metadata or {}).get("article_candidates"):
                return True
        return False

    @staticmethod
    def _split_sentences_with_spans(text: str) -> List[Tuple[str, int, int]]:
        raw = str(text or "")
        if not raw.strip():
            return []

        spans: List[Tuple[str, int, int]] = []
        start = 0
        for idx, char in enumerate(raw):
            if char in "。！？；\n":
                chunk = raw[start : idx + 1].strip()
                if chunk:
                    spans.append((chunk, start, idx + 1))
                start = idx + 1
        tail = raw[start:].strip()
        if tail:
            spans.append((tail, start, len(raw)))
        return spans

    @staticmethod
    def _tokenize_overlap_terms(text: str) -> Set[str]:
        tokens = set()
        source = text or ""
        for item in re.findall(r"[A-Za-z0-9一-龥]{2,}", source):
            value = item.strip().lower()
            if len(value) >= 2:
                tokens.add(value)
        # 中文语料常无空格，补充2-gram以提升 claim-evidence 对齐稳定性。
        for chunk in re.findall(r"[一-龥]{2,}", source):
            normalized = chunk.strip().lower()
            if len(normalized) < 2:
                continue
            for idx in range(0, len(normalized) - 1):
                tokens.add(normalized[idx : idx + 2])
        return tokens

    def _must_terms_hit_ratio(self, text: str, must_terms: List[str]) -> float:
        terms = [str(item or "").strip().lower() for item in (must_terms or []) if str(item or "").strip()]
        if not terms:
            return 0.0
        compact = (text or "").lower()
        hits = sum(1 for term in terms if term in compact)
        return round(hits / float(len(terms)), 4)

    def _build_draft_claims(self, answer: str, max_claims: int = 4) -> List[str]:
        compact = re.sub(r"\s+", " ", str(answer or "")).strip()
        if not compact:
            return []
        raw_sentences = [s.strip() for s in re.split(r"(?<=[。！？；!?;])\s*", compact) if s.strip()]
        claims: List[str] = []
        for sentence in raw_sentences:
            if len(sentence) < 10:
                continue
            if any(skip in sentence for skip in ["不构成法律意见", "仅供参考", "无法确定"]):
                continue
            claims.append(sentence)
            if len(claims) >= max_claims:
                break
        if claims:
            return claims
        return [compact[:120]]

    def _find_best_evidence(self, claim_text: str, documents: List[Document]) -> Dict[str, Any]:
        claim_terms = self._tokenize_overlap_terms(claim_text)
        if not claim_terms:
            claim_terms = self._tokenize_overlap_terms((claim_text or "")[:50])

        best: Dict[str, Any] = {
            "doc": None,
            "score": 0.0,
            "start_sent_idx": -1,
            "end_sent_idx": -1,
            "char_start": -1,
            "char_end": -1,
            "text": "",
        }

        for doc in documents or []:
            sent_spans = self._split_sentences_with_spans(doc.page_content or "")
            if not sent_spans:
                continue
            for sent_idx, (sentence, char_start, char_end) in enumerate(sent_spans):
                sent_terms = self._tokenize_overlap_terms(sentence)
                if not sent_terms:
                    continue
                overlap = len(claim_terms.intersection(sent_terms))
                if overlap <= 0:
                    continue
                ratio = overlap / float(max(1, len(claim_terms)))
                if ratio > best["score"]:
                    best = {
                        "doc": doc,
                        "score": ratio,
                        "start_sent_idx": sent_idx,
                        "end_sent_idx": sent_idx,
                        "char_start": char_start,
                        "char_end": char_end,
                        "text": sentence[:220],
                    }
        return best

    @staticmethod
    def _contains_any(text: str, terms: List[str]) -> bool:
        source = (text or "").lower()
        for term in terms or []:
            value = str(term or "").strip().lower()
            if value and value in source:
                return True
        return False

    def _match_article(self, target_articles: List[str], law_name: str, article_id: str, evidence_text: str) -> bool:
        if not target_articles:
            return False
        combined = " ".join([law_name or "", article_id or "", evidence_text or ""])
        return self._contains_any(combined, target_articles)

    def _match_law(self, target_laws: List[str], law_name: str, evidence_text: str) -> bool:
        if not target_laws:
            return bool((law_name or "").strip())
        combined = " ".join([law_name or "", evidence_text or ""])
        return self._contains_any(combined, target_laws)

    def verify_and_refine(
        self,
        question: str,
        claims: List[str],
        documents: List[Document],
        answer_mode: str = "strong",
    ) -> List[Dict[str, Any]]:
        article_candidates = self._extract_article_candidates(question, documents)
        law_candidates = self._extract_law_candidates(question, documents)
        must_terms = self._extract_must_terms(documents)
        is_article_intent = self._is_article_intent(question, documents, article_candidates)
        refined: List[Dict[str, Any]] = []

        for idx, claim_text in enumerate(claims, start=1):
            evidence = self._find_best_evidence(claim_text, documents)
            doc = evidence.get("doc")
            md = (doc.metadata or {}) if doc is not None else {}
            law_name = str(md.get("law_name", "") or "")
            article_id = str(md.get("article_id", "") or "")
            doc_id = str(md.get("chunk_id", md.get("node_id", "")) or "").strip()
            evidence_text = str(evidence.get("text", "") or "")
            if not doc_id and evidence_text:
                doc_id = f"auto_{abs(hash((law_name, article_id, evidence_text[:80])))}"

            has_doc_id = bool(doc_id)
            has_evidence = bool(evidence_text)
            law_match = self._match_law(law_candidates, law_name, evidence_text)
            article_match = self._match_article(article_candidates, law_name, article_id, evidence_text)
            if is_article_intent and not law_candidates:
                law_match = False
            must_hit_ratio = self._must_terms_hit_ratio(f"{claim_text} {evidence_text}", must_terms)
            semantic_ok = float(evidence.get("score", 0.0) or 0.0) >= 0.2
            evidence_short = len(evidence_text) < 20

            verdict = "unsupported"
            if not has_evidence:
                verdict = "unsupported"
            elif is_article_intent:
                if law_match and article_match and semantic_ok and not evidence_short:
                    verdict = "supported"
                elif law_match and not article_match and must_hit_ratio >= 0.5:
                    verdict = "weak"
                elif article_match and semantic_ok:
                    verdict = "weak"
                elif law_match or article_match or must_hit_ratio >= 0.2:
                    verdict = "weak"
                else:
                    verdict = "unsupported"
            else:
                if law_match and must_hit_ratio >= 0.5 and semantic_ok and not evidence_short:
                    verdict = "supported"
                elif law_match or must_hit_ratio >= 0.2 or semantic_ok:
                    verdict = "weak"
                else:
                    verdict = "unsupported"

            refined.append(
                {
                    "claim_id": f"c{idx}",
                    "claim_text": claim_text,
                    "doc_id": doc_id,
                    "law_name": law_name,
                    "article_id": article_id,
                    "evidence_span": {
                        "start_sent_idx": int(evidence.get("start_sent_idx", -1)),
                        "end_sent_idx": int(evidence.get("end_sent_idx", -1)),
                        "char_start": int(evidence.get("char_start", -1)),
                        "char_end": int(evidence.get("char_end", -1)),
                        "text": evidence_text,
                    },
                    "verdict": verdict,
                    "meta": {
                        "article_intent": is_article_intent,
                        "has_doc_id": has_doc_id,
                        "law_match": law_match,
                        "article_match": article_match,
                        "must_terms_hit_ratio": must_hit_ratio,
                        "semantic_score": round(float(evidence.get("score", 0.0) or 0.0), 4),
                        "evidence_short": evidence_short,
                        "answer_mode": (answer_mode or "strong").lower(),
                    },
                }
            )
        return refined

    def _compose_refined_answer(
        self,
        refined_claims: List[Dict[str, Any]],
        question: str,
        documents: List[Document],
        answer_mode: str = "strong",
    ) -> str:
        supported = [item for item in (refined_claims or []) if item.get("verdict") == "supported"]
        weak = [item for item in (refined_claims or []) if item.get("verdict") == "weak"]
        mode = (answer_mode or "strong").lower()

        lines: List[str] = []
        for item in supported:
            law = str(item.get("law_name", "") or "")
            article = str(item.get("article_id", "") or "")
            citation = " ".join(x for x in [law, article] if x).strip()
            if citation:
                lines.append(f"{item.get('claim_text', '')}（依据：{citation}）")
            else:
                lines.append(str(item.get("claim_text", "") or ""))

        for item in weak:
            text = str(item.get("claim_text", "") or "")
            lines.append(f"基于当前证据，倾向认为：{text}")

        if not lines:
            return self._build_insufficient_answer(question, documents)

        if mode == "weak" and lines:
            lines.insert(0, "当前证据强度一般，以下结论请谨慎参考。")

        answer = "\n\n".join(lines)
        return self._post_process_answer(self._ensure_disclaimer(answer), answer_mode=mode)

    def generate_refined_answer(
        self,
        question: str,
        documents: List[Document],
        answer_mode: str = "strong",
    ) -> Dict[str, Any]:
        if (answer_mode or "").lower() == "insufficient":
            answer = self._build_insufficient_answer(question, documents)
            return {"answer": answer, "draft_claims": [], "refined_claims": []}

        draft_answer = self.generate_adaptive_answer(
            question=question,
            documents=documents,
            answer_mode=answer_mode,
        )
        draft_claims = self._build_draft_claims(draft_answer)
        refined_claims = self.verify_and_refine(
            question=question,
            claims=draft_claims,
            documents=documents,
            answer_mode=answer_mode,
        )
        final_answer = self._compose_refined_answer(
            refined_claims=refined_claims,
            question=question,
            documents=documents,
            answer_mode=answer_mode,
        )
        return {
            "answer": final_answer or draft_answer,
            "draft_claims": draft_claims,
            "refined_claims": refined_claims,
        }

    def generate_adaptive_answer(
        self,
        question: str,
        documents: List[Document],
        answer_mode: str = "strong",
    ) -> str:
        if (answer_mode or "").lower() == "insufficient":
            return self._build_insufficient_answer(question, documents)

        prompt = self._build_prompt(question, documents, answer_mode=answer_mode)
        try:
            response = self._create_generation_completion(
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                timeout=60,
            )
            raw_answer = response.choices[0].message.content.strip()
            return self._post_process_answer(
                self._ensure_disclaimer(raw_answer),
                answer_mode=(answer_mode or "strong").lower(),
            )
        except Exception as e:
            return self._build_degraded_answer(documents, e)

    def generate_adaptive_answer_stream(
        self,
        question: str,
        documents: List[Document],
        max_retries: int = 1,
        answer_mode: str = "strong",
    ):
        _ = max_retries  # 保留参数以兼容历史调用签名。
        if (answer_mode or "").lower() == "insufficient":
            yield self._build_insufficient_answer(question, documents)
            return

        prompt = self._build_prompt(question, documents, answer_mode=answer_mode)
        try:
            response = self._create_generation_completion(
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                timeout=60,
            )
            print("开始流式生成回答...\n")

            full_response = ""
            for chunk in response:
                if chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    full_response += delta
                    yield delta

            # 流式收敛后做免责声明后校验，若缺失自动补全
            # if self.enable_legal_disclaimer and not self._has_disclaimer(full_response):
            #     logger.warning("流式输出未命中免责声明，已自动追加 disclaimer_appended=true")
            #     yield f"\n\n{self.DISCLAIMER_TEXT}"
            return
        except Exception as e:
            yield self._build_degraded_answer(documents, e)
            return
