# Header Detector – Required Behavior
- Address-like lines must **not** be headers.
- Measurement/units lines (±, mm/in, IPxx, A/V/Hz) must **not** be headers.
- RFQ parenthetical headers like `1) Scope` **must** be detected.
- Appendix (`Appendix A - ...`) and letter-number (`A.1 Title`) **must** be detected.
