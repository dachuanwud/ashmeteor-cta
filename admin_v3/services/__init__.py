"""Service boundaries for admin_v3.

These modules keep pure calculation, exchange access, and persistence helpers
separate from Flask routes and scheduler jobs.  Existing public functions remain
as compatibility wrappers while callers migrate gradually.
"""

