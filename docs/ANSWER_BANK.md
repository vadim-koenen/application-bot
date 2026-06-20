# Application Answer Bank

`config/application_answer_bank.yaml` contains reusable, claim-linked answers.

Approved fields include website, LinkedIn, business identity, current
positioning, desired role type, location preference, and conservative
interest/fit language.

Guarded fields:

- compensation: `REVIEW_REQUIRED` unless an exact range is approved
- work authorization: `PENDING_USER_APPROVAL`
- sponsorship: `PENDING_USER_APPROVAL`
- background and legal-sensitive questions: `REVIEW_REQUIRED`
- unknown required questions: `REVIEW_REQUIRED`

An answer marked approved is withheld if its supporting claim is not approved
for the `application_answer` context. No metric is generated.
