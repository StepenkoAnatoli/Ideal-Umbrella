Incident Report: Checkout API outage

Summary: On 2026-10-14 between 14:02 and 14:31 UTC, the checkout API returned HTTP 503 errors for approximately 38% of requests. The incident was triggered by the deployment of release v2.14.0, which introduced a new environment variable (PAYMENT_TIMEOUT_MS) that was not set in the production configuration. As a result, the payment client initialised with a timeout of zero milliseconds and every call to the payment provider failed immediately.

Timeline:
- 14:02 UTC: Deployment of v2.14.0 completed.
- 14:05 UTC: Alert fired for elevated 5xx rate on checkout-api.
- 14:12 UTC: On-call engineer identified the missing variable in the pod logs.
- 14:20 UTC: Rollback to v2.13.2 initiated.
- 14:31 UTC: Error rate returned to baseline.

Impact: Roughly 1,900 checkout attempts failed; no data was lost and no double charges occurred.

Root cause: Missing configuration value in production; the deployment pipeline does not validate required environment variables.

Action items:
1. Add a startup check that fails fast when a required variable is absent (owner: platform team, due 2026-10-21).
2. Add PAYMENT_TIMEOUT_MS to the production config with a value of 8000.
3. Add a pre-deploy config diff step to the pipeline.