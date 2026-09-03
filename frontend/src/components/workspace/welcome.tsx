"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo } from "react";

import { usePromptInputController } from "@/components/ai-elements/prompt-input";
import { Suggestion } from "@/components/ai-elements/suggestion";
import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

import { AuroraText } from "../ui/aurora-text";

let waved = false;

export function Welcome({
  className,
  mode,
  onStarterClick,
}: {
  className?: string;
  mode?: "ultra" | "pro" | "thinking" | "flash";
  onStarterClick?: (prompt: string) => void;
}) {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const { textInput } = usePromptInputController();
  const isUltra = useMemo(() => mode === "ultra", [mode]);
  const colors = useMemo(() => {
    if (isUltra) {
      return ["#efefbb", "#e9c665", "#e3a812"];
    }
    return ["var(--color-foreground)"];
  }, [isUltra]);
  useEffect(() => {
    waved = true;
  }, []);

  const handleStarterClick = useCallback(
    (prompt: string) => {
      if (onStarterClick) {
        onStarterClick(prompt);
        return;
      }
      textInput.setInput(prompt);
      setTimeout(() => {
        const form =
          document.querySelector<HTMLFormElement>(
            "form:has(textarea[name='message'])",
          ) || document.querySelector<HTMLFormElement>("form");
        form?.requestSubmit();
      }, 0);
    },
    [onStarterClick, textInput],
  );

  const descriptionLines = t.welcome.description.split("\n").filter(Boolean);
  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-2xl flex-col items-center justify-center gap-2 px-4 pt-4 pb-3 text-center",
        className,
      )}
    >
      <div className="text-2xl font-bold">
        {searchParams.get("mode") === "skill" ? (
          `✨ ${t.welcome.createYourOwnSkill} ✨`
        ) : (
          <div className="flex items-center gap-2">
            <div className={cn("inline-block", !waved ? "animate-wave" : "")}>
              {isUltra ? "🚀" : "👋"}
            </div>
            <AuroraText colors={colors}>{t.welcome.greeting}</AuroraText>
          </div>
        )}
      </div>
      {searchParams.get("mode") === "skill" ? (
        <div className="text-muted-foreground text-sm">
          {t.welcome.createYourOwnSkillDescription.includes("\n") ? (
            <pre className="font-sans whitespace-pre">
              {t.welcome.createYourOwnSkillDescription}
            </pre>
          ) : (
            <p>{t.welcome.createYourOwnSkillDescription}</p>
          )}
        </div>
      ) : (
        <div className="text-muted-foreground max-w-xl text-sm leading-relaxed">
          {descriptionLines.map((line) => (
            <p key={line} className="break-keep whitespace-nowrap">
              {line}
            </p>
          ))}
        </div>
      )}

      {searchParams.get("mode") !== "skill" &&
        t.welcome.starterQuestions?.length > 0 && (
          <div className="mt-1 flex w-full flex-wrap items-center justify-center gap-2">
            {t.welcome.starterQuestions.map((item) => (
              <Suggestion
                key={item.prompt}
                className="shrink-0 rounded-full border border-border/70 bg-background/60 px-3.5 py-1.5 text-xs text-muted-foreground shadow-2xs backdrop-blur-xs transition-colors hover:bg-muted hover:text-foreground"
                suggestion={item.suggestion}
                onClick={() => handleStarterClick(item.prompt)}
              />
            ))}
          </div>
        )}
    </div>
  );
}
