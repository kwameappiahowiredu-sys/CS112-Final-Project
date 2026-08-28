# Test Plan and Test-Case Document

CS 112 course project. Covers the analysis pipeline, GridCare-Lite, ClinicCare-Lite and the
interactions between them.

## 1. Approach

Testing runs continuously rather than at the end. Every rule that can be stated as "the
system must refuse X" is written as a test that asserts the refusal, because a system that
accepts bad input quietly is worse than one that crashes.

Three principles shaped the suite:

1. **Test the service layer, not the widgets.** Both applications keep their rules in plain
   Python functions that take data and return results or raise. That is why the whole
   GridCare-Lite workflow can be tested without a display, and the whole ClinicCare-Lite
   workflow without a browser.
2. **Negative tests carry the weight.** Roughly half the suite asserts that something is
   refused: a wrong role, an invalid transition, an unsupported file, another patient's
   record.
3. **Skip honestly.** Tests that depend on analysis output skip with a message naming the
   script to run, rather than failing. A partial checkout reports what it could not check.

## 2. Running the suite

```
python tests/run_tests.py
```

Individual modules:

```
python -m unittest tests.test_grid_data
python -m unittest tests.test_gridcare_lite
python -m unittest tests.test_cliniccare_lite
python -m unittest tests.test_integration
```

Key-derivation cost is reduced inside the test modules (PBKDF2 iterations and the bcrypt
cost factor) and restored afterwards, so the suite runs in seconds. Separate tests assert
the production settings are still strong, so the speed-up cannot hide a weakened default.

## 3. Test levels

| Level | Where | What it covers |
| --- | --- | --- |
| Unit | `test_cliniccare_lite.py`, `test_gridcare_lite.py` | Validators, hashing, state machines, completeness checks, storage |
| Component | Same files | A whole workflow inside one application |
| Data | `test_grid_data.py` | Invariants of the raw, cleaned, integrated and analysed datasets |
| Integration | `test_integration.py` | Module interactions and agreement between artefacts |
| System | Manual, `docs/demonstration_script.md` | The end-to-end demonstration on both applications |
| Security | Spread across all files | Access control, path traversal, credential handling |
| Usability | Manual | Role dashboards, error messages, mobile widths |

## 4. Test cases

Each row states the objective, the input, and the expected outcome. Actual outcome and pass
or fail are recorded in section 6 from the most recent run.

### 4.1 Data pipeline

| ID | Objective | Input | Expected |
| --- | --- | --- | --- |
| D-01 | Generator is reproducible | `generate_datasets.py` with seed 42 | 10 utilities, 44 substations, 55 lines |
| D-02 | Primary keys unique | Each raw CSV | No duplicate IDs |
| D-03 | No missing values | Each raw CSV | Every cell non-empty |
| D-04 | Referential integrity | `lines.csv` | Every endpoint and utility ID resolves |
| D-05 | No self-referencing lines | `lines.csv` | Source never equals destination |
| D-06 | No duplicate undirected pairs | `lines.csv` | Each substation pair appears once |
| D-07 | Coordinates plausible | `substations.csv` | Latitude 3 to 16, longitude -18 to 5 |
| D-08 | Voltages in domain | Both CSVs | Every value in {11, 33, 69, 161, 330} |
| D-09 | Positive magnitudes | Both CSVs | Capacity and length above zero |
| D-10 | Lengths exceed geodesic | `lines.csv` | Recorded length between 0.99x and 2x the haversine distance |
| D-11 | Cleaning preserves rows | Clean CSVs | Same row counts as raw |
| D-12 | Country labels standardised | Clean substations | No `Cote` or `Burkina`; full names present |
| D-13 | Derived columns exist | Clean lines | Geodesic distance and length ratio present, ratio within 1.0 to 2.0 |
| D-14 | Denormalised names match | Clean lines | Endpoint names equal the register |
| D-15 | Integration loses nothing | Master datasets | Row counts preserved; no unmatched join keys |
| D-16 | Degree sum consistent | `master_substations.csv` | Sum of connections equals twice the line count |
| D-17 | Voltage inconsistency flagged | `master_lines.csv` | At least one `Voltage Consistent` is False |

### 4.2 Network and analysis outputs

| ID | Objective | Input | Expected |
| --- | --- | --- | --- |
| N-01 | Every substation scored | `node_metrics.csv` | 44 rows, IDs match the register |
| N-02 | Graph size matches data | `global_metrics.csv` | 44 nodes, 55 edges |
| N-03 | Centralities normalised | `node_metrics.csv` | Every value between 0 and 1 |
| N-04 | PageRank sums to one | `node_metrics.csv` | Total 1.0 to two decimal places |
| N-05 | Criticality tiers valid | `criticality_ranking.csv` | Only Critical, High, Moderate, Low |
| N-06 | Ranking ordered | `criticality_ranking.csv` | Scores descending |
| N-07 | Bridges are real lines | `bridge_lines.csv` | Every line ID exists; count matches global metrics |
| N-08 | Contingency consistent | `n1_node_contingency.csv` | Components at least 1; separated count never negative |
| N-09 | Fragmentation detected | `n1_node_contingency.csv` | At least one substation fragments the network |
| N-10 | Nearest neighbours valid | Geo tables | Distance above zero; never a substation's own name |
| N-11 | Regional counts add up | `regional_density.csv` | Sum equals 44 |
| N-12 | Utility line counts add up | `utility_territory.csv` | Sum equals 55 |
| N-13 | Interactive map written | `interactive/grid_map.html` | File exists |
| N-14 | Risk scores bounded | `regional_reliability.csv` | Between 0 and 1 |
| N-15 | Recommendations generated | `strategic_recommendations.csv` | At least one, valid priorities, non-empty actions |
| N-16 | Documentation facts agree | `headline_facts.json` | Counts match the cleaned data |

### 4.3 GridCare-Lite

| ID | Objective | Input | Expected |
| --- | --- | --- | --- |
| G-01 | Schema created | Fresh database | All seven tables present |
| G-02 | Foreign keys enforced | `PRAGMA foreign_keys` | Returns 1 |
| G-03 | Unknown substation rejected at DB level | Direct insert with bad ID | `IntegrityError` |
| G-04 | Role constraint | Insert role `superuser` | `IntegrityError` |
| G-05 | Status constraint | Insert status `Cancelled` | `IntegrityError` |
| G-06 | One work order per outage | Second insert for same outage | `IntegrityError` |
| G-07 | Register imported | Fresh database | 44 substations, 55 lines |
| G-08 | Import idempotent | Second import | Zero rows added |
| G-09 | Valid login | admin1 with correct password | User returned with role |
| G-10 | Wrong password | admin1 with wrong password | None |
| G-11 | Unknown user | Non-existent username | None |
| G-12 | Empty password | Blank password | None |
| G-13 | No plaintext storage | Users table | Hash contains no password text |
| G-14 | Salting works | Two users, same password | Different hashes |
| G-15 | Hash round trip | Known password | Verifies; wrong case fails; malformed hash fails |
| G-16 | Production KDF cost | Module constant | At least 100,000 iterations |
| G-17 | Permission matrix | 11 role and capability pairs | Matches the documented table |
| G-18 | Technician cannot log outage | Technician calls create | `PermissionError` |
| G-19 | Engineer cannot assign | Engineer calls assign | `PermissionError` |
| G-20 | Customer service cannot resolve | Service calls resolve | `PermissionError` |
| G-21 | Technician ownership | Other technician completes | `PermissionError` |
| G-22 | Full workflow | Log, assign, complete, resolve | Statuses progress; resolution recorded |
| G-23 | Status history | Same workflow | Five events in the correct order |
| G-24 | Unknown substation | Outage against ID 999999 | `ValueError` |
| G-25 | Blank description | Whitespace only | `ValueError` |
| G-26 | Invalid severity | `Catastrophic` | `ValueError` |
| G-27 | Duplicate outage | Same description while unresolved | `ValueError` |
| G-28 | Duplicate allowed once resolved | Same description after resolution | New outage created |
| G-29 | Invalid date format | `01-09-2026` | `ValueError` |
| G-30 | Non-technician assignee | Assign the administrator | `ValueError` |
| G-31 | Second work order | Assign twice | `ValueError` |
| G-32 | Work notes required | Blank notes | `ValueError` |
| G-33 | Re-completion blocked | Complete twice | `ValueError` |
| G-34 | Resolved cannot reopen | Resolved to In Progress | `ValueError` |
| G-35 | Resolved takes no work order | Assign after resolution | `ValueError` |
| G-36 | Complaint logged | Valid complaint | Stored and retrievable |
| G-37 | Complaint links to outage | Valid outage ID | Link recorded |
| G-38 | Complaint rejects unknown outage | ID 4242 | `ValueError` |
| G-39 | Complaint requires fields | Blank name or details | `ValueError` |
| G-40 | Report accuracy | Two outages, one resolved | Summary counts match |
| G-41 | Regional totals | Two outages | Totals sum to two |
| G-42 | Outage filters | By region and status | Correct subsets |
| G-43 | Technician scope | Two technicians | Each sees only their own work orders |

### 4.4 ClinicCare-Lite

| ID | Objective | Input | Expected |
| --- | --- | --- | --- |
| C-01 | Clinician IDs | Eight digits ending 0000 | Role clinician |
| C-02 | Patient years 2022 to 2028 | Each year | Role patient |
| C-03 | Years outside window | 2021, 2029, 1999, 2030 | Rejected |
| C-04 | Malformed IDs | Wrong length, letters, spaces, empty | Rejected |
| C-05 | Role mismatch reported | Clinician ID where patient expected | One error |
| C-06 | Password rules | Five failing passwords | Each names its rule |
| C-07 | Overlong password | Over 72 bytes | Rejected |
| C-08 | bcrypt round trip | Known password | Verifies; wrong password and malformed hash fail |
| C-09 | Production cost factor | Module constant | At least 10 |
| C-10 | Registration by role | Valid clinician and patient | Correct roles assigned |
| C-11 | Clinic attachment | New patient | Added to the clinic roster |
| C-12 | Duplicate ID | Same ID twice | Rejected; one user stored |
| C-13 | Invalid ID at registration | 12345678 | Rejected; no user stored |
| C-14 | Weak password at registration | `password` | Rejected |
| C-15 | Confirmation mismatch | Different confirmation | Rejected |
| C-16 | Invalid email | `not-an-email` | Rejected |
| C-17 | Missing name | Whitespace | Rejected |
| C-18 | No plaintext password | Stored record | bcrypt hash only, no password field |
| C-19 | Login routing | Each role | Correct dashboard |
| C-20 | Wrong password | Valid ID, wrong password | Rejected |
| C-21 | Unknown user | Unregistered ID | Rejected |
| C-22 | Empty credentials | Blank | Rejected |
| C-23 | Last login recorded | After login | Timestamp set |
| C-24 | Logout clears session | After logout | Protected page redirects |
| C-25 | Anonymous access | Eight protected routes | All redirect to login |
| C-26 | Patient blocked from clinician pages | Six routes | All refused |
| C-27 | Clinician blocked from patient pages | Three routes | All refused |
| C-28 | No cross-patient leakage | Patient dashboard | Other patient's name absent |
| C-29 | Clinician roster | Clinician dashboard | Patient names present |
| C-30 | Theme validation | Valid and invalid themes | Accepted and refused |
| C-31 | Unknown route | `/no-such-page` | 404 |
| C-32 | Task creation notifies | New task | Patients notified |
| C-33 | Task validation | Missing title, bad date | Both errors reported |
| C-34 | Patient must be in clinic | Unknown patient ID | Rejected |
| C-35 | Patients cannot create tasks | Patient calls create | `AuthorisationError` |
| C-36 | Submission renamed and stored | Upload | `patientID_taskID.csv` on disk |
| C-37 | Versioning | Second upload | `_v2` suffix, version 2 |
| C-38 | Unsupported type | `.exe` | Rejected |
| C-39 | Oversized file | 3 MB | Rejected |
| C-40 | Empty file | Zero bytes | Rejected |
| C-41 | Unassigned task | Other patient submits | `AuthorisationError` |
| C-42 | Clinician cannot submit | Clinician submits | `AuthorisationError` |
| C-43 | Unknown task | TASK9999 | Rejected |
| C-44 | Review records metadata | Valid review | Outcome, reviewer, timestamp stored; patient notified |
| C-45 | Outcomes categorical | Outcome `85` | Rejected |
| C-46 | Pending not a review | Outcome `Pending` | Rejected |
| C-47 | Patients cannot review | Patient reviews | `AuthorisationError` |
| C-48 | Cross-clinic review | Outside clinician | `AuthorisationError` |
| C-49 | Task status view | Before, after, reviewed | Not submitted, Awaiting review, outcome |
| C-50 | Overdue detection | Past due date | Status Overdue |
| C-51 | Well-formed CSV | Expected fields present | Complete, no issues |
| C-52 | Missing column | Absent date column | Named in the issues |
| C-53 | Empty and malformed cells | Blank and text in numeric column | Both reported |
| C-54 | Header without data | Header only | Reported |
| C-55 | Text submission labels | Labelled lines | Complete |
| C-56 | Missing text label | Absent label | Incomplete |
| C-57 | PDF not checked | PDF upload | Not checked |
| C-58 | No interpretation | Reading of 240/150 | Complete; no evaluative word appears |
| C-59 | Path traversal in identifiers | `../../etc` | `ValueError` |
| C-60 | Path traversal on read | `../../data/users.json` | `ValueError` |
| C-61 | Owner download | Own submission | 200 with the file bytes |
| C-62 | Cross-patient download | Another patient's file | Refused |
| C-63 | Clinic clinician download | Clinic submission | 200 |
| C-64 | CSV preview | Stored CSV | Table rows returned |
| C-65 | PDF preview | Stored PDF | Marked unavailable |
| C-66 | Patient messages clinician | Valid message | Delivered |
| C-67 | Patient to patient blocked | Patient recipient | `AuthorisationError` |
| C-68 | Cross-clinic messaging | Outside clinician | `AuthorisationError` |
| C-69 | Empty message | Whitespace | Rejected |
| C-70 | Unknown recipient | Unregistered ID | Rejected |
| C-71 | Thread privacy | Third party | No threads visible |
| C-72 | Unread tracking | Message then read | Count rises then clears |
| C-73 | Announcement reach | New announcement | Every patient notified |
| C-74 | Patients cannot announce | Patient posts | `AuthorisationError` |
| C-75 | Expired announcements | Past expiry | Hidden |
| C-76 | Notification scoping | Message to one patient | Absent from the other's inbox |
| C-77 | Email fallback | SMTP unconfigured | Status `recorded`; outbox written |
| C-78 | No hard-coded credentials | Email handler source | Reads environment variables only |
| C-79 | Appointment scheduling | Valid appointment | Created and notified |
| C-80 | Invalid datetime | `not-a-date` | Rejected |
| C-81 | Patient outside clinic | Other clinic patient | Rejected |
| C-82 | Invalid status | `Rescheduled` | Rejected |
| C-83 | Attendance points | Marked Attended | Engagement points rise |
| C-84 | On-time beats late | Two patients | On-time patient scores higher |
| C-85 | Streak counting | Two on-time tasks | Streak of two |
| C-86 | Engagement privacy | Patient history page | Privacy note shown; no other patient named |
| C-87 | Reminder pass | Appointment in six hours | Reminded once, not twice |
| C-88 | Completion rate | Two uploads, one patient | 50 percent of two assignments |
| C-89 | Pending review count | Before and after review | One then zero |
| C-90 | No-show rate | One attended, one no-show | 50 percent |
| C-91 | Overdue counted | Past-due task | At least one overdue |
| C-92 | Clinic scoping | Two clinics | Each sees only its own |
| C-93 | Patient history scope | Two patients | Each sees only their own |
| C-94 | Collections created | Fresh store | All eight JSON files |
| C-95 | Unknown collection | `secrets` | `ValueError` |
| C-96 | Truncation bug absent | Large payload then small | Exactly the small payload |
| C-97 | Corrupt JSON | Malformed file | Reads as empty |
| C-98 | Model round trip | Save and reload a task | Identical dictionary |
| C-99 | ID increment | Two tasks | TASK0001 then TASK0002 |
| C-100 | Scope notice | Login and register pages | Non-diagnostic notice present |
| C-101 | Messaging notice | Login page | Not-monitored notice present |
| C-102 | Outcomes carry no score | Every outcome | No digits |
| C-103 | No ranking route | URL map | No leaderboard, ranking or compare route |
| C-104 | Privacy rule stated | Patient dashboard | States that patients are not ranked |

### 4.5 Integration

| ID | Objective | Input | Expected |
| --- | --- | --- | --- |
| I-01 | Register reaches the application | Cleaned CSV into SQLite | Every substation with matching name and region |
| I-02 | Assets outside the register refused | ID beyond the highest | `ValueError` |
| I-03 | Critical asset through the workflow | Top-ranked substation | Region report shows one outage, one resolved |
| I-04 | Complaint joins outage and asset | Linked complaint | Join returns the substation and outage status |
| I-05 | Line endpoints survive import | Imported lines | No orphans |
| I-06 | Journey recorded end to end | Full workflow | Five history events in order |
| I-07 | ClinicCare journey across modules | Assign to review | Notifications, status, metrics, engagement and history all agree |
| I-08 | Appointment across modules | Attendance marked | Engagement rises, no-show rate updates |
| I-09 | Web layer matches services | Task created over HTTP | Service layer shows the same task and fields |
| I-10 | No cross-patient notification | Task for one patient | Absent from the other's inbox |
| I-11 | Network tables cover the estate | Node metrics | Same IDs as the register |
| I-12 | Bridges are real lines | Bridge table | Every ID in the line register |
| I-13 | Recommendations reference real places | Recommendation areas | Region, utility, substation or National |
| I-14 | Reliability regions match | Reliability table | Exactly the register's regions |
| I-15 | Documentation facts agree | Headline facts | Counts match the cleaned data |

## 5. Defect log

Defects found during development and their resolution.

| ID | Severity | Description | Found by | Resolution | Retest |
| --- | --- | --- | --- | --- | --- |
| DEF-01 | Medium | Generator writes truncated country labels (`Cote`, `Burkina`) from `country.split()[0]` | D-12 | Standardised in cleaning and recorded as a transformation | Pass |
| DEF-02 | High | Fifteen lines rated above the lower-voltage substation they terminate on | Task 1.1 validation | Flagged for engineering review, not silently corrected | Pass |
| DEF-03 | Medium | Two substations terminate no line, so the graph is disconnected before any failure | Task 1.1 validation | Diameter and path length computed on the largest component; isolation reported | Pass |
| DEF-04 | High | Document's graph template keys nodes by short name but adds edges by full name, creating duplicate nodes | Code review of the provided template | Graph keyed by Substation ID throughout | Pass |
| DEF-05 | Medium | Report claimed higher voltage carries longer runs; the data shows 161 kV shortest and 11 kV long | Cross-check against the data | Report now computes the correlation and explains the generator's behaviour | Pass |
| DEF-06 | Medium | Capacity utilisation flagged 33 of 42 substations as over-subscribed | Cross-check against the data | Reframed as a rating-consistency finding; recommendation changed to reconcile the fields | Pass |
| DEF-07 | Low | Completion rate counted raw submissions, so two uploads by one patient read as two completions | C-88 | Counts distinct patient and task pairs | Pass |
| DEF-08 | Low | N-1 separated count went negative for isolated substations | Review of the contingency table | Clamped at zero and scoped to substations in the core | Pass |
| DEF-09 | Low | Test asserted on the response object rather than its body | C-30 | Assert on `response.data` | Pass |
| DEF-10 | Low | Reminder test scheduled an appointment at the current minute, which parses as slightly past | C-87 | Test schedules six hours ahead, inside the reminder window | Pass |
| DEF-11 | Medium | Suite took minutes because every test derived production-strength hashes | Test run timing | Cost reduced in tests, with separate assertions on the production constants | Pass |

## 6. Most recent run

| Module | Tests | Result |
| --- | --- | --- |
| `test_grid_data.py` | Raw dataset invariants | Pass |
| `test_grid_data.py` | Clean, integrated and analysis outputs | Skipped where the producing script has not been run |
| `test_gridcare_lite.py` | 46 | Pass |
| `test_cliniccare_lite.py` | 107 | Pass |
| `test_integration.py` | 10 | Pass, one class skipped pending analysis output |

Record the totals from `python tests/run_tests.py` here after each run.

## 7. Manual test checklist

Automated tests cannot cover appearance, layout or the feel of an interaction. Before the
demonstration, walk these by hand.

**Usability**

- Every error message names what is wrong and what to do about it.
- No screen requires horizontal scrolling at 1366 pixels wide.
- Tab order follows reading order on every form.
- Destructive or irreversible actions state their consequence before they are taken.

**Responsive behaviour (ClinicCare-Lite)**

- 360 pixels wide: navigation wraps, tables remain readable, forms usable.
- 768 pixels: two-column layouts collapse cleanly.
- 1366 pixels and above: content stays within its maximum width rather than stretching.

**Browser compatibility**

- Chrome, Firefox and Edge at current versions.
- Both themes in each browser.

**Security spot checks**

- Log in as a patient, copy a clinician URL, paste it while logged in as a patient.
- Log out, then use the browser back button to reach a protected page.
- Edit a submission ID in a download URL to one belonging to another patient.
- Confirm no page source contains a password, hash or SMTP credential.

**Failure handling**

- Stop mid-upload and confirm no partial submission is recorded.
- Corrupt one JSON collection by hand and confirm the application still starts.
- Run ClinicCare-Lite with no SMTP configuration and confirm notifications still arrive
  in the in-app inbox.
