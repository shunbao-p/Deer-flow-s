---
name: runtime-skill-builder
description: Create, validate, package, and install a minimal new skill during agent runtime when no existing skill fits, normal tools are not sufficient, and the task is worth turning into a reusable workflow. Use only after the runtime skill-creation policy allows it. Do not use for one-off, temporary, ambiguous, or ordinary tasks that normal tools can already complete well.
---

# Runtime Skill Builder

Use this skill only after the lead agent has already decided that automatic skill creation is allowed for the current task.
Before using this skill, the agent should have already called `evaluate_skill_lifecycle` and received `NO_MATCH`, then called `evaluate_skill_creation` and received `ALLOW`.

## Hard Guardrails

Never use this skill when any of the following is true:

- An existing skill already covers the task well enough
- Normal tools can complete the task with stable, acceptable quality
- The request is one-off, temporary, ambiguous, or still missing key requirements
- The workflow cannot be described as reusable steps with clear inputs and outputs

Your goal is not to build a perfect framework. Your goal is to build the smallest reusable skill that solves the recurring workflow safely.

## Output Standard

Prefer a minimal skill directory with only:

- `SKILL.md`

Add extra files only when they are necessary for correctness or repeatability. First version defaults to a single-file skill.

## Working Location

Create the draft skill inside the current thread workspace, not directly inside `skills/custom`.

Recommended layout:

```text
/mnt/user-data/workspace/runtime-skills/<skill-name>/
  SKILL.md
```

Write the packaged archive to:

```text
/mnt/user-data/outputs/runtime-skills/<skill-name>.skill
```

## Step 1: Reconfirm the Preconditions

Before writing anything, quickly verify all of these:

1. `evaluate_skill_lifecycle` already returned `NO_MATCH`.
2. `evaluate_skill_creation` already returned `ALLOW`.
3. No existing skill is sufficient.
4. No similar custom skill should be reused or updated in place instead.
5. Normal tools are not a stable or efficient fit.
6. The task is reusable and has stable steps.
7. You can describe clear trigger conditions, inputs, outputs, and basic validation.

If any item fails, stop and do not create a skill.
If `evaluate_skill_lifecycle` found an existing custom skill, prefer reusing it.
If that skill is disabled but still the best fit, re-enable it with `enable_skill`.
If it needs adjustment, update it in place with `update_custom_skill`.

## Step 2: Design the Minimal Skill

Decide the minimum reusable workflow:

- What user intent should trigger the skill
- What fixed steps the skill should enforce
- What output shape the skill should produce
- What common mistakes the skill should prevent

Choose a stable, descriptive skill name. Do not create version-spam names such as `foo-v2` unless it is truly a different workflow.

## Step 3: Write `SKILL.md`

Create a minimal `SKILL.md` with:

1. YAML frontmatter
2. A direct workflow body

Frontmatter must contain:

- `name`
- `description`

Rules:

- `name` must match the intended installed skill identity
- `description` must explain both what the skill does and when to use it
- The body should be imperative, concise, and focused on repeatable execution
- Keep the file lean; avoid auxiliary docs unless they are genuinely needed

## Step 4: Validate Before Packaging

Before packaging, check at minimum:

- `SKILL.md` exists
- frontmatter parses cleanly
- `name` and `description` are present and non-empty
- the body contains an actual workflow, not placeholders
- the skill is still worth reusing and not just a one-off workaround

If you find a problem, fix it before packaging. Do not install a broken draft.

## Step 5: Package the Skill

Use the existing packaging script from the public `skill-creator` skill:

```bash
python /mnt/skills/public/skill-creator/scripts/package_skill.py /mnt/user-data/workspace/runtime-skills/<skill-name> /mnt/user-data/outputs/runtime-skills
```

Expected result:

```text
/mnt/user-data/outputs/runtime-skills/<skill-name>.skill
```

## Step 6: Install the Packaged Skill

After packaging succeeds, call:

```python
install_skill(
    path="/mnt/user-data/outputs/runtime-skills/<skill-name>.skill",
    source="runtime_auto_create",
    expected_skill_name="<skill-name>",
)
```

Rules:

- Install only through `install_skill`
- Never write directly into `skills/custom`
- If installation fails, read the error, fix the skill or package, and retry only when the fix is concrete
- If the skill already exists, do not keep generating near-duplicate skills in the same thread

## Step 7: After Installation

After successful installation:

1. Tell the user the skill was created and installed.
2. State that the skill will be available in later messages in the same thread.
3. Continue the task using ordinary tools for the current turn if needed.
4. Do not assume the current turn has already reloaded the new skill prompt.

## Quality Bar

The created skill should be:

- small
- reusable
- clear about trigger conditions
- clear about the workflow steps
- better than repeating the same ad hoc reasoning every time

If you cannot meet that bar, do not create the skill.
