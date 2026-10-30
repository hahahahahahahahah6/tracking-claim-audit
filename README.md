# Cross-frame following claim audit

An offline, dependency-free Python 3.9+ checker comparing documentation promises
about following objects across video frames with Python provider fingerprints.
Source files are parsed with AST and never executed.

Install and run:

```sh
pip install tracking-claim-audit
tracking-claim-audit ./project --json
python3 -m tracking_claim_audit ./project --verbose
tracking-claim-audit ./project --ignore 'vendor/*' --fail-on MEDIUM
tracking-claim-audit --version
```

The root README.md and Markdown files beneath any docs path component supply
claims. Fenced blocks using backticks or tildes are omitted; inline code counts.
Blank lines delimit paragraphs; wrapped lines join. Case, contractions, hyphens,
and whitespace are normalized. Exact word-boundary templates are matched longest
first, with denial spans removed before positive matching.

Python evidence comes from OpenCV constructor calls (including legacy providers),
ultralytics YOLO instances with a track method call, norfair Tracker, supervision
ByteTrack, DeepSort/DeepSORT from deep_sort or deep_sort_realtime, Sort from sort,
and dlib correlation_tracker. Import aliases resolve within a module; local
bindings shadow imported names. Construction suffices except for YOLO, which
also needs the method invocation. No vision dependencies are installed.

The two rules are:

```text
documented-tracking-claim-false: HIGH without production evidence; MEDIUM with only test evidence
documented-no-tracking-claim-false: HIGH when denial conflicts with production evidence
```

At most one finding is emitted per rule. With no claim, the result is PASS.
Tests are separated from production by a tests component or test_*.py / *_test.py
filename. Files beneath fixtures, docs, and examples supply no source evidence.
Symbolic links are excluded. Invalid Python supplies no evidence. Repeatable
--ignore patterns use fnmatch against relative POSIX file paths.

Exit 0 means PASS at the chosen threshold; 2 means FAIL; 1 means invalid input,
unreadable input, or command usage error. The default threshold is HIGH, so a
MEDIUM finding still yields PASS unless --fail-on MEDIUM is selected. JSON has
verdict, findings (rule, severity, message), and files_scanned fields. Human
output prints the verdict and findings; --verbose adds the scanned file count.

This is static evidence, not a runtime correctness guarantee. Imports alone,
image loading, frame capture, box drawing, per-frame detection, segmentation,
classification, face/hand/pose detectors, OCR, barcode decoding, flow estimation,
and standalone Kalman filters do not qualify. Hand-written IoU box association
has no supported provider fingerprint. Strings, shell commands, subprocesses,
unbound method calls, and locally defined lookalikes do not qualify. Dynamic
imports, cross-module model provenance, and arbitrary alias propagation are
unsupported. Binding analysis is conservative across each module, so rebinding
a provider or model can suppress evidence even before the rebinding statement.

Build and test with python3 -m build and python3 -m unittest discover. The source
archive includes the unittest suite and its fixtures. This project uses MIT terms.
