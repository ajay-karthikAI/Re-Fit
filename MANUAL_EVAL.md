# Phase 3 Manual Stopwatch Eval

Automated checks can prove the kit assembles cleanly. They cannot prove the
3-minute claim. Complete all three timed runs below before declaring Phase 3
done or tagging `phase-3`.

Exit criterion: each run uses a real application form for a tracked job target
and finishes in 3:00 or less using only the Apply Kit screen. Any field ordering
mismatch, missing-but-common field, or generated answer that needs more than a
trivial edit is a product bug to patch before rerunning.

## Instructions

1. Open a real Greenhouse/Lever/Ashby posting matching one of your tracked job targets.
2. Start the timer.
3. Fill the real application using ONLY the Apply Kit screen. Do not go back to
   the resume, profile, job-target, dashboard, notes, or source files.
4. Stop on submit.
5. Record: total time, any field that required leaving the kit screen, and any
   copy that needed hand-editing before pasting.
6. If the run surfaces a field ordering mismatch or missing common field, patch
   `app/data/ats_fields.py`, regenerate the kit, and rerun.
7. If generated short-answer copy needed more than trivial hand-editing, patch
   `app/services/short_answers.py` or its tests, regenerate the answer, and rerun.

## Run 1: Greenhouse

- Date:
- Tester:
- Job target:
- Real posting URL:
- Browser/application URL:
- Apply Kit URL:
- Timer start:
- Timer stop:
- Total time:
- Submitted successfully? yes/no:
- Under 3:00? yes/no:

### Fields That Required Leaving The Kit

| Field | Why leaving the kit was necessary | Fix needed? |
| --- | --- | --- |
|  |  |  |

### Copy That Needed Hand-Editing

| Field | Original kit copy | Edit made | Trivial? yes/no | Fix needed? |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Ordering / Missing Field Bugs

| Issue | File to patch | Fixed before rerun? |
| --- | --- | --- |
|  | `app/data/ats_fields.py` |  |

### Notes


## Run 2: Lever

- Date:
- Tester:
- Job target:
- Real posting URL:
- Browser/application URL:
- Apply Kit URL:
- Timer start:
- Timer stop:
- Total time:
- Submitted successfully? yes/no:
- Under 3:00? yes/no:

### Fields That Required Leaving The Kit

| Field | Why leaving the kit was necessary | Fix needed? |
| --- | --- | --- |
|  |  |  |

### Copy That Needed Hand-Editing

| Field | Original kit copy | Edit made | Trivial? yes/no | Fix needed? |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Ordering / Missing Field Bugs

| Issue | File to patch | Fixed before rerun? |
| --- | --- | --- |
|  | `app/data/ats_fields.py` |  |

### Notes


## Run 3: Ashby

- Date:
- Tester:
- Job target:
- Real posting URL:
- Browser/application URL:
- Apply Kit URL:
- Timer start:
- Timer stop:
- Total time:
- Submitted successfully? yes/no:
- Under 3:00? yes/no:

### Fields That Required Leaving The Kit

| Field | Why leaving the kit was necessary | Fix needed? |
| --- | --- | --- |
|  |  |  |

### Copy That Needed Hand-Editing

| Field | Original kit copy | Edit made | Trivial? yes/no | Fix needed? |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### Ordering / Missing Field Bugs

| Issue | File to patch | Fixed before rerun? |
| --- | --- | --- |
|  | `app/data/ats_fields.py` |  |

### Notes

