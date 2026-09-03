---
name: agents-delay-execution
description: Delays execution of the current request for a user-specified duration, then resumes and completes that same request. Use only when explicitly invoked for requests such as "execute this plan after 2 hours," "wait 30 minutes, then deploy," or "sleep before continuing."
---

# Agents · Delay Execution

Use the duration in the invoking message as the delay and treat the rest of that message as the deferred task. Preserve all of its instructions and scope.

1. Parse the duration into a positive whole number of seconds. If no unambiguous duration is present, ask the user for one. Do not reinterpret a clock time or date as a duration.
2. Before starting any work on the deferred task, tell the user how long execution will wait and what will resume afterward.
3. Execute one Bash sleep command with the duration passed as a positional argument, never interpolated as shell code:

   ```bash
   bash -lc 'sleep "$1"' _ <seconds>
   ```

4. Let the command yield into a persistent tool session when the tool supports it. Wait or poll that same session until the sleep process exits successfully. Keep progress updates brief and no more than 60 seconds apart when the harness requires ongoing commentary.
5. Do not perform, precompute, delegate, schedule, remind, or otherwise begin the deferred task while the sleep process is running. Do not substitute an automation or timer for the Bash command.
6. After the sleep command succeeds, resume the original message and complete the deferred task normally, including any applicable skills, checks, approvals, and safety constraints.

If the process is interrupted or the session cannot survive the requested delay, do not claim the delay completed. Report the interruption and continue waiting for only the verified remaining duration when it can be determined safely; otherwise ask the user how to proceed.
