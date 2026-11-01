# Meghraj Reconciliation — deployment staging

Source staging for the **Reconciliation Changes** dashboard extension.

**Not a production release.** Current Cloud Run backend/database source is not present in this repository. Do not deploy this folder as an independently running financial application.

The patch performs read-only comparisons of uploaded invoice numbers and Payment Received fields. It does not settle invoices, mutate the database, or overwrite financial statuses.

See `staging/reconciliation-changes/README.md` for integration requirements.
