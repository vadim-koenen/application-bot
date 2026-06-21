# Claim Inventory

`config/resume_claim_inventory.yaml` is the candidate-fact boundary for packet
generation. A posting can influence which approved themes are emphasized, but
it cannot create a new candidate claim.

`config/claim_evidence.yaml` is the approval ledger. Each claim records its
status, evidence source/detail, permitted contexts, confidence, approval
requirement, and verification date.

## Approved content

The inventory currently approves Vadim Koenen’s name, Koenen Revenue Systems /
KRS as the current business identity, public contact assets, and the
positioning themes explicitly supplied for this project. Approved metrics are
intentionally empty.

## Claim gaps

Requirements involving exact tenure, education, credentials, employment
history, quantified achievements, named-platform proficiency, work
authorization, compensation, or legal answers are not inferred. They become
claim-gap identifiers in a review packet.

## Approving a new claim

1. Obtain the exact statement and supporting source from Vadim.
2. Add a stable ID and conservative text under `approved_experience_claims` or
   `approved_metrics`.
3. Narrow a conflicting prohibited pattern only when the evidence supports it.
4. Add a test proving the claim works while adjacent unsupported claims remain blocked.
5. Review the generated packet before any future live operation.

Never paste a job requirement into the inventory as if it were candidate
experience.

Approval statuses are `APPROVED`, `APPROVED_FROM_USER_CONTEXT`,
`APPROVED_FROM_RESUME`, `APPROVED_FROM_WEBSITE`,
`PENDING_USER_APPROVAL`, `REJECTED`, and `DO_NOT_USE`. Only approved statuses
can be used, and only in explicitly allowed and evidence-matched contexts.
