IPEDS public flagship admissions, fall 2015-2024
Compiled November 28, 2026

FILES
ipeds_flagship_admissions_2015_2024.csv: Main analysis file. One row per
university and entering fall year: 50 universities x 10 years = 500 rows.
495 rows have an acceptance rate; five retain missing values as empty fields.

ipeds_flagship_admissions_changes_2015_2024.csv: One row per university,
showing the two endpoints and their percentage-point difference. The UMD
endpoint difference crosses a reporting break and is not a clean trend estimate.

ipeds_flagship_admissions_benchmarks_2015_2024.csv: Annual comparisons with
the same 47 peers throughout. Excludes UMD itself, Alaska Fairbanks (missing
2022-2024 admissions), and Penn State (changes in reporting units).

ipeds_flagship_admissions_sources.csv: Official download URLs, selected ZIP
members, SHA-256 archive hashes, retrieval date, and source row counts for all
30 ADM, HD, and IC tables. Raw downloads are cached outside this repository.

WHAT THIS MEASURES
IPEDS Admissions (ADM) counts first-time, degree/certificate-seeking
undergraduate applicants, offers of admission, and enrolled students. The
federal definition includes full-time and part-time students, early action
and early decision, and students who started in the preceding summer.
It does not measure graduate or transfer admission.

Acceptance rate = 100 x ADMSSN / APPLCN.
Yield rate = 100 x ENRLT / ADMSSN.
Rate columns are numeric percentages on a 0-100 scale: 44.794858 means
44.794858%, not 0.44794858%. Rates are rounded to six decimal places.
Changes and UMD-minus-peer gaps are percentage points, not percent changes.
Lower acceptance rates indicate greater institutional selectivity, but do
not establish how much harder admission is for an equally qualified person.

PERIOD AND RELEASES
Fall 2015 through fall 2024 are ten annual observations (nine elapsed years).
Fall 2024 was the latest admissions year available at compilation. The
2025-26 fall collection release does not include the winter admissions
component. Do not confuse collection year, data year, and release year.

The revised (_rv) CSV inside each official archive is preferred when present.
ADM2015-ADM2023 use revised/final members. ADM2024 is provisional and can
change. The source manifest records exactly which member was used. HD
directory and IC characteristics tables are joined within the same year on
UNITID. UTF-8 and legacy Windows-1252 encodings are handled explicitly.

COMPARISON GROUP
This is a fixed, conventional one-flagship-per-state comparison group, not
every public four-year college or every institution called a flagship.
The roster corresponds to the fifty-school list at:
https://collegebenchmark.com/categories/flagship-universities

Flagship is an analytical choice, not a formal IPEDS category. All selected
institutions have public control in HD2024. New York is represented by the
University at Buffalo, not Buffalo State. Stony Brook and other additional
flagships are outside this particular roster. Other examples are UC Berkeley,
University of Arizona, University of Oregon, and Penn State Main Campus.
The exact roster and stable UNITIDs are present in the main CSV.

IMPORTANT UMD BREAK IN FALL 2021
UMD defines its newer first-time group as including new freshmen, Freshmen
Connection, and new Applied Agriculture students. Its earlier new-freshmen
group excludes Freshmen Connection and Applied Agriculture. UMD states that
the newer group starts in fall 2021, and its admissions report identifies
pre-2021 data as new freshmen only. This break is marked on all UMD rows.

UMD's reported IPEDS rates are 44.875853% in 2015, 52.027579% in 2021, and
44.794858% in 2024. The 2015-2024 endpoints alone cannot resolve the hypothesis
because their populations differ. The 2021-2024 decline is 7.232721 percentage
points and uses the newer group, although it still does not control for who
applies, application policies, or changes in available seats.

For a consistent decade-long UMD series, ask its Office of Institutional
Research, Planning & Assessment for the same population for every year:
either new freshmen only throughout, or all first-time students throughout.
Ask specifically how Freshmen Connection offers and enrollment are counted.
Do not splice in local dashboard or Common Data Set counts without checking
population, revision date, and whether summer entrants are included.

MISSING VALUES AND OTHER CAUTIONS
Alaska Fairbanks has no ADM record in 2022, 2023, or 2024 and reports an open
admission policy in the corresponding IC files. Those rates remain blank;
they are not estimated as 100% or zero.

Penn State Main Campus UNITID 214777 has no ADM record in 2020 or 2021.
Penn State reported as a university-wide unit, UNITID 495767, during those
years. System totals are deliberately not substituted for a main-campus
series. Penn State is retained with notes and excluded from peer benchmarks.

The flags R and C mean reported and analyst-corrected, respectively. Nevada
Reno's 2023 enrolled count has flag C. All other available selected counts
have flag R. Blank source flags on the five missing rows mean no ADM record.
The full dictionary also defines flags for imputations and unavailable data.

These historical ADM totals do not separate in-state and out-of-state
applicants/admissions, majors, admission rounds, or applicant qualifications.
For a Maryland resident's chances, request residency-specific data from UMD
and the comparison schools. Application counts are not unique people across
universities: the same person can apply to multiple institutions.

BENCHMARKS AND TESTING THE HYPOTHESIS
The mean gives each of the 47 peer universities equal weight. The median
describes the middle peer. The pooled rate is sum(admitted)/sum(applicants),
which weights institutions by application volume. It is not the share of
unique people accepted somewhere. These measures answer different questions.

In 2024 UMD's rate is 44.794858%, versus a peer mean of 67.916056% and a peer
median of 75.533735%. That describes current relative selectivity. It does
not by itself demonstrate an increasing relative difficulty over ten years.

Plot all annual rates, examine UMD's gap from peers, and compare changes in
percentage points. A more negative UMD-minus-peer gap means a lower UMD rate
relative to peers. Address UMD's 2021 break before fitting a decade-long
trend. Consider separate 2015-2020 and 2021-2024 comparisons and verify any
other institutional reporting changes before publication. This roster does
not support claims about all public universities.

MAIN CSV DATA DICTIONARY
unitid: Stable IPEDS identifier of the selected institution.
institution: Institution name in the 2024 directory, used as a stable label.
state: Two-letter state abbreviation.
fall_year: Entering fall class year.
ipeds_collection_year: Admissions collection label, e.g. 2024-25.
institution_name_in_year: Name in that year's HD directory, blank if absent.
open_admission_policy_code: IC OPENADMP; 1=yes, 2=no. Other source codes, if
  present, are retained. Blank means no usable value for that unit/year.
umd_reporting_population: UMD population description; blank for other schools.
applicants: ADM APPLCN, first-time undergraduate applicants.
admitted: ADM ADMSSN, applicants offered admission.
enrolled_first_time: ADM ENRLT, admitted first-time students who enrolled.
acceptance_rate_pct: Calculated admitted/applicants x 100.
yield_rate_pct: Calculated enrolled/admitted x 100.
applicants_status, admitted_status, enrolled_status: ADM source flags.
admissions_file: Exact CSV member selected from the official ZIP archive.
data_release: Admissions release type, not the directory's release type.
source_url: Official admissions ZIP download for that row.
retrieved_date: Retrieval date, YYYY-MM-DD.
notes: Known population changes or missing records.
included_in_peer_benchmark: 1 for the fixed 47 peers, 0 otherwise.

VALIDATION AND REPRODUCTION
The compilation checks unique UNITID-year keys, 50 schools and 10 years,
same-year joins, public control, state identities, and nonnegative counts
with enrolled <= admitted <= applicants. All calculated acceptance and yield
rates were independently checked with spreadsheet formulas. Missing values
are preserved. Revised counts can differ slightly from campus snapshots.

Rebuild from the repository root with:
python3 scripts/compile_ipeds_flagship_admissions.py

ADDITIONAL PRIMARY SOURCES
IPEDS complete data files:
https://nces.ed.gov/ipeds/datacenter/DataFiles.aspx?gotoReportId=7&rtid=1&year=2024
2024 admissions data dictionary:
https://nces.ed.gov/ipeds/complete-data-files/ADM2024_Dict.zip
Release schedule:
https://nces.ed.gov/ipeds/survey-components/data-release-schedule
UMD population definitions:
https://www.irpa.umd.edu/InstitutionalData/datadefinitions.html
UMD admissions report with the historical population note:
https://www.irpa.umd.edu/CampusCounts/Fall2024/Admissions/apps_ug.pdf
NCES guidance on institutional reporting units:
https://nces.ed.gov/ipeds/use-the-data/institutional-groupings-in-ipeds
Penn State explanation of consolidated reporting:
https://www.psu.edu/news/administration/story/penn-state-updates-ipeds-data-reporting-accordance-us-guidance-changes
