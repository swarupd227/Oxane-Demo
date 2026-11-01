# Presenter guide

Oxane AI-assisted onboarding, about 20 minutes plus 10 for questions. Steps 3, 6 and 7 carry most of the value, so never cut them.

## Before you go on

1. Start the stack and open http://localhost:5180.

```powershell
docker compose up -d --build
```

2. Wait until the deal page shows, then press `Alt+R` to reset the case.
3. Press `Alt+P` for large text on a projector. It fits 1920×1080 without scrolling.
4. Check that the deal bar reads **Sandbox** and **Recorded run**.
5. Keep `tests/e2e/fallback-recordings` open in a video player.

No key or internet connection is needed. Every result replays from the recorded run.

## Keys

| Key | Action |
|---|---|
| `Alt+R` | Reset the case, keeping the old session in the log |
| `Alt+P` | Large text on or off |
| `Ctrl+K` | Command menu |
| `]` and `[` | Next and previous step |
| `J` and `K` | Move through a list |
| `A` | Approve or accept |
| `E` | Edit a term |
| `Q` | Hold a term, or draft a query on an exception |
| `X` | Escalate an exception |

## Say this at the start

All documents and data are synthetic, written to resemble real US auto ABF practice. This is not connected to Panorama. In a pilot, this would extend Accelerate, not replace it.

## Script

| Step | Time | Do | Say |
|---|---|---|---|
| 1 Deal | 1 min | Show the deal summary | The fictional deal, and Oxane's role as verification agent |
| 2 Intake | 2 min | Load the pack | Every file is classified, and Schedule 4 is flagged before anyone reads a page. Code finds it, not the model |
| 3 Terms | 4 min | Click Advance rate, drag the date across 1 March, click Facility limit | Every value opens its source. Code checks each quote exists in the document, and Tier 1 needs a person whatever the confidence |
| 4 Rules | 3 min | Edit E5 to 70,000, show the preview, save with a reason | The analyst stays in control. The change is pending, and the run still uses the approved rules |
| 5 Mapping | 2 min | Show the mapping and the derived field, accept | Weighted average APR isn't on the tape, so it's derived and labelled |
| 6 Validation | 3 min | Run the tape, click each bridge row | **Slow down here.** The gap is explained to the cent. The certificate tested 60 days past due, not 30. Then the shared VINs: possible double pledging, within this pool only |
| 7 Exceptions | 3 min | Draft the X4 query, escalate X5, accept X6 | Accepting the dealer match recalculates live, and availability falls below Calderwood's alert |
| 8 Approve | 1 min | Show the block, switch to the second analyst, decline the rule change, approve | Four-eyes is enforced by the server, and the log can't be changed |
| 9 Scorecard | 1 min | Open a row | The formula sits behind each number. Then give the honest caveat below |

## Keep the claims honest

Say these plainly:

- Prompts were tuned on this one synthetic pack, so these results are not independent.
- Across three fresh runs on the earlier build, all 10 exceptions were found and all Tier 1 values were correct each time. Some lower-tier fields varied.
- No time saving is quoted, because there is no Oxane baseline yet.
- The double-pledging check covers one pool. Cross-lender checks need data rights that are unresolved.
- Every Tier 1 value needs a person. The system does not approve data.

Don't say that this will reach these numbers on real deals, that Accelerate would be replaced, or that the load file matches Panorama.

## If something goes wrong

| Problem | Do this |
|---|---|
| A screen shows an error banner | Press its retry button |
| Something looks wrong mid-flow | `Alt+R`, then step forward |
| The app won't load | Play that step's recording from `tests/e2e/fallback-recordings` |
| A page is blank just after a restart | Wait 10 seconds and reload |

## Likely questions

| Question | Answer |
|---|---|
| Is this live? | No. It replays a recorded run on synthetic data. A live run takes about 3.5 minutes and costs under US$1 |
| Why did the scan show low confidence? | Any value read from an image goes to a person, by design |
| Who is signed in? | The two analyst roles are switched on screen for now. Real sign-in comes with deployment |
| Where would it run? | In Oxane's tenant for a pilot, with their approved model |
