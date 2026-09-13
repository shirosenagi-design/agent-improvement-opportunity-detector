PROJECT 04 — USER MODEL V4
==========================

PURPOSE LOCK
------------
Broadly safe / broadly acceptable AI behavior is the baseline, not the enemy.

The experiment asks:
Can a small amount of person-specific information help an AI reason more effectively
with one individual — and can an evaluation agent detect what that personalization
recovered, what it lost, and what a developer should consider changing?

COLD-START SHORTCUT
-------------------
Input:
1. self-reported MBTI
2. a short self-introduction
3. the user's actual question

The high-capability model then infers a PROVISIONAL USER MODEL.
MBTI is only a weak seed. The person's own description and current task are stronger evidence.

There is NO fixed INFJ -> ENTP mapping in V4.

LIVE AGENT FLOW
---------------
free-form question
-> prepare synthetic population
-> infer provisional user model (live model reasoning)
-> generate Population Mode answer
-> generate Personalized Mode answer through the user model
-> deterministic supporting measurements
-> PROJECT 04 semantic comparison
-> 1-3 developer hypotheses
-> HUMAN REVIEW (terminal; no automatic update)

FASTEST UPGRADE FROM V3
-----------------------
1. Close the current RUN_WINDOWS.cmd server window.
2. Extract project04_user_model_v4_PATCH_ONLY.zip into the SAME V3 folder you are using.
3. Replace/overwrite matching files.
4. SETUP_WINDOWS.cmd is NOT needed again. Dependencies are unchanged.
5. Start RUN_WINDOWS.cmd again and refresh the browser.
6. Enter:
   - a user message
   - MBTI
   - a short self-introduction
7. Run one new Research Trial.

No API key is included.
No API call was made while building this ZIP.
Codex was not used.
