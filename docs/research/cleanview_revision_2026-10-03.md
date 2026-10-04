# Cleanview diagnosis and corrected regional land support

This user-requested post-inspection revision compares the deterministic current
model against public operating-facility listings, then fixes supported defects.
The complete findings, run differential, browser evidence, debug/fix chain logs,
review, executable freeze and completion record live in
`runs/cleanview_revision_v1/`. The revised model run is
`runs/cleanview_regional_v2/`; comparison artifacts are separate diagnostic
outputs and never feed weights or physical calculations.

The completed revision evaluates the same 152,500 cells and 305,000
design/scenario alternatives. It restores 2,770 alternatives to conditional
consideration, retains 330 hard failures, and publishes 2,326 bounded
region/design alternatives. All five raw metrics, native geography/provenance
and selected physical quantities are exact against the baseline; retained
rankable scores are unchanged. All 792 tests passed. The execution freeze v2
is preserved; delivery freeze v3 records only a separately reviewed comparison
checksum-label repair. The current comparison is
`runs/cleanview_revised_comparison_v1/comparison_report.md`.

The confirmed original defect is spatial: the single-cell minimum-land rule
was applied independently to 1 km cells while the output is a multi-cell search
region. Two neighboring cells with 0.30 km² classified land each may support the
0.40468564224 km² project-assumed total, but both were rejected. The repair marks
that positive insufficient cell evidence critical UNKNOWN for regional search,
then rejects bounded components whose complete total remains insufficient.
Unknown aggregate support stays null. Adequate total land never proves parcel
contiguity, ownership, zoning or access.

Annual energy/carbon/water units and decision invariants passed verification.
Dry-cooling dominance follows from declared equal PUE and differing WUE rather
than observed performance. Coarse polygon transmission distance and partial
fine coverage remain explicit limits. Existing sites are not optimum-sustainability
labels and cannot determine the model's preferences or engineering coefficients.

These geographic regions deserve further investigation under the stated
facility requirements, datasets, constraints, assumptions, and decision
preferences. They are not proven buildable parcels. Compatible independent
operating measurements and exact locations are needed before physical error or
predictive accuracy can be estimated.
