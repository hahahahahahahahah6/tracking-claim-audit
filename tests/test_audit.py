import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tracking_claim_audit.audit import audit, claims, evidence
from tracking_claim_audit.phrases import TRACKING, NOTRACKING

FIXTURES = Path(__file__).parent / 'fixtures'


class ClaimsTests(unittest.TestCase):
    def test_fences(self):
        for marker in ('```', '~~~', '   ````'):
            self.assertEqual(claims(marker + '\ntracks objects\n' + marker), (False, False))

    def test_inline(self):
        self.assertEqual(claims('`tracks objects`'), (True, False))

    def test_negative_removal(self):
        for phrase in NOTRACKING:
            with self.subTest(phrase=phrase):
                self.assertEqual(claims(phrase), (False, True))

    def test_all_positive_templates(self):
        for phrase in TRACKING:
            self.assertEqual(claims(phrase), (True, False))

    def test_hyphens(self):
        self.assertEqual(claims('multi-object tracking'), (True, False))

    def test_contraction(self):
        self.assertEqual(claims("doesn't track objects"), (False, True))

    def test_paragraphs(self):
        self.assertEqual(claims('tracks\nobjects'), (True, False))
        self.assertEqual(claims('tracks\n\nobjects'), (False, False))

    def test_boundaries(self):
        self.assertEqual(claims('distracks objectsx'), (False, False))

    def test_longest(self):
        self.assertEqual(claims('does not track objects across frames; tracks people'), (True, True))
        for phrases in (TRACKING, NOTRACKING):
            self.assertEqual(list(phrases), sorted(phrases, key=len, reverse=True))
            self.assertEqual(len(phrases), len(set(phrases)))


class EvidenceTests(unittest.TestCase):
    pass


POSITIVE = {
    'cv_direct': 'import cv2\ncv2.TrackerCSRT_create()',
    'cv_alias': 'import cv2 as c\nc.TrackerKCF_create()',
    'cv_from': 'from cv2 import TrackerMIL_create as T\nT()',
    'cv_legacy': 'import cv2\ncv2.legacy.TrackerMOSSE_create()',
    'cv_legacy_from': 'from cv2.legacy import MultiTracker_create\nMultiTracker_create()',
    'yolo_bound': 'from ultralytics import YOLO\nm = YOLO("x")\nm.track()',
    'yolo_chain': 'import ultralytics as u\nu.YOLO("x").track()',
    'norfair': 'import norfair\nnorfair.Tracker()',
    'norfair_from': 'from norfair import Tracker as T\nT()',
    'supervision': 'import supervision\nsupervision.ByteTrack()',
    'sv': 'import supervision as sv\nsv.ByteTrack()',
    'supervision_from': 'from supervision import ByteTrack\nByteTrack()',
    'deep': 'import deep_sort_realtime\ndeep_sort_realtime.DeepSort()',
    'deep_from': 'from deep_sort_realtime.deepsort_tracker import DeepSort as D\nD()',
    'deep_upper': 'from deep_sort import DeepSORT\nDeepSORT()',
    'sort': 'import sort\nsort.Sort()',
    'sort_from': 'from sort import Sort as S\nS()',
    'dlib': 'import dlib\ndlib.correlation_tracker()',
    'dlib_from': 'from dlib import correlation_tracker as C\nC()',
}
NEGATIVE = {
    'import': 'import cv2',
    'image': 'import cv2\ncv2.imread("x")',
    'pil': 'from PIL import Image\nImage.open("x")',
    'camera': 'import cv2\ncv2.VideoCapture(0)',
    'drawing': 'import cv2\ncv2.rectangle(image, box)',
    'detection': 'from torchvision.models.detection import fasterrcnn_resnet50_fpn\nfasterrcnn_resnet50_fpn()',
    'yolo_alone': 'from ultralytics import YOLO\nm=YOLO("x")',
    'yolo_predict': 'from ultralytics import YOLO\nm=YOLO("x")\nm.predict()',
    'yolo_call': 'from ultralytics import YOLO\nm=YOLO("x")\nm()',
    'segmentation': 'import mediapipe as mp\nmp.solutions.selfie_segmentation.SelfieSegmentation()',
    'classification': 'import timm\ntimm.create_model("x")',
    'face': 'import cv2\ncv2.CascadeClassifier("x").detectMultiScale(img)',
    'hand': 'import mediapipe as mp\nmp.solutions.hands.Hands()',
    'pose': 'import mediapipe as mp\nmp.solutions.pose.Pose()',
    'ocr': 'import easyocr\neasyocr.Reader(["en"])',
    'barcode': 'from pyzbar.pyzbar import decode\ndecode(img)',
    'flow': 'import cv2\ncv2.calcOpticalFlowFarneback(a,b)',
    'kalman': 'import cv2\ncv2.KalmanFilter()\nfrom filterpy.kalman import KalmanFilter\nKalmanFilter()',
    'shadow': 'from norfair import Tracker\nclass Tracker: pass\nTracker()',
    'shadow_cv': 'import cv2\ncv2 = custom\ncv2.TrackerCSRT_create()',
    'shadow_yolo': 'from ultralytics import YOLO\ndef YOLO(): pass\nYOLO().track()',
    'shadow_deep': 'from deep_sort import DeepSort\ndef DeepSort(): pass\nDeepSort()',
    'shadow_byte': 'from supervision import ByteTrack\nclass ByteTrack: pass\nByteTrack()',
    'shadow_sort': 'from sort import Sort\nclass Sort: pass\nSort()',
    'unbound': 'whatever.track()',
    'string': 's = "cv2.TrackerCSRT_create() tracking"',
    'subprocess': 'import subprocess\nsubprocess.run(["tracker"])',
    'invalid': 'import cv2\ncv2.TrackerCSRT_create((',
    'other_sort': 'from something import Sort\nSort()',
    'other_provider': 'from something import TrackerCSRT_create, YOLO, correlation_tracker\nTrackerCSRT_create()\nYOLO().track()\ncorrelation_tracker()',
    'rebound_model': 'from ultralytics import YOLO\nm=YOLO()\nm=other\nm.track()',
}


def evidence_test(source, expected):
    def test(self):
        self.assertEqual(evidence(source), expected)
    return test


for name, source in POSITIVE.items():
    setattr(EvidenceTests, 'test_positive_' + name, evidence_test(source, True))
for name, source in NEGATIVE.items():
    setattr(EvidenceTests, 'test_negative_' + name, evidence_test(source, False))


class IntegrationTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'tracking_claim_audit', *map(str, args)], capture_output=True, text=True)

    def test_good(self):
        self.assertEqual(audit(FIXTURES / 'good')['findings'], [])

    def test_bad(self):
        result = self.run_cli(FIXTURES / 'bad', '--json')
        self.assertEqual(result.returncode, 2)
        self.assert_finding(json.loads(result.stdout), 'HIGH', 'documented-tracking-claim-false')

    def assert_finding(self, result, severity, rule):
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['severity'], severity)
        self.assertEqual(result['findings'][0]['rule'], rule)

    def test_testonly(self):
        for extra, code in [([], 0), (['--fail-on', 'MEDIUM'], 2)]:
            result = self.run_cli(FIXTURES / 'testonly', '--json', *extra)
            self.assertEqual(result.returncode, code)
            self.assert_finding(json.loads(result.stdout), 'MEDIUM', 'documented-tracking-claim-false')

    def test_denial(self):
        result = self.run_cli(FIXTURES / 'no_tracking', '--json')
        self.assertEqual(result.returncode, 2)
        self.assert_finding(json.loads(result.stdout), 'HIGH', 'documented-no-tracking-claim-false')

    def test_no_claim(self):
        self.assertEqual(audit(FIXTURES / 'no_claim')['verdict'], 'PASS')

    def test_ignore(self):
        self.assertEqual(audit(FIXTURES / 'bad', ['README.*'])['verdict'], 'PASS')

    def test_json(self):
        result = json.loads(self.run_cli(FIXTURES / 'good', '--json').stdout)
        self.assertEqual(set(result), {'verdict', 'findings', 'files_scanned'})
        self.assertEqual(result['files_scanned'], 2)

    def test_verbose(self):
        self.assertIn('Files scanned: 2', self.run_cli(FIXTURES / 'good', '--verbose').stdout)

    def test_version(self):
        result = self.run_cli('--version')
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '0.1.0'))

    def test_invalid_root(self):
        self.assertEqual(self.run_cli(FIXTURES / 'absent').returncode, 1)

    def test_usage(self):
        for args in ([], ['--unknown'], [str(FIXTURES), '--fail-on', 'LOW']):
            self.assertEqual(self.run_cli(*args).returncode, 1)

    def test_excluded_source(self):
        for relative in ('fixtures/x.py', 'docs/x.py', 'examples/x.py'):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / 'README.md').write_text('tracks objects')
                target = root / relative
                target.parent.mkdir()
                target.write_text(POSITIVE['cv_direct'])
                self.assert_finding(audit(root), 'HIGH', 'documented-tracking-claim-false')

    def test_test_names(self):
        for relative in ('test_x.py', 'x_test.py', 'tests/x.py'):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / 'README.md').write_text('tracks objects')
                target = root / relative
                target.parent.mkdir(exist_ok=True)
                target.write_text(POSITIVE['cv_direct'])
                self.assert_finding(audit(root), 'MEDIUM', 'documented-tracking-claim-false')

    def test_docs_scope_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'other.md').write_text('tracks objects')
            self.assertEqual(audit(root)['files_scanned'], 0)
            (root / 'nested/docs').mkdir(parents=True)
            (root / 'nested/docs/claim.md').write_text('tracks objects')
            (root / 'source.txt').write_text(POSITIVE['cv_direct'])
            (root / 'linked.py').symlink_to(root / 'source.txt')
            (root / 'loop').symlink_to(root, target_is_directory=True)
            self.assert_finding(audit(root), 'HIGH', 'documented-tracking-claim-false')
            self.assertEqual(audit(root)['files_scanned'], 1)

    def test_both_families(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'README.md').write_text('tracks objects\n\ndoes not track objects')
            self.assertEqual(len(audit(root)['findings']), 1)
            (root / 'app.py').write_text(POSITIVE['cv_direct'])
            self.assert_finding(audit(root), 'HIGH', 'documented-no-tracking-claim-false')


if __name__ == '__main__':
    unittest.main()
