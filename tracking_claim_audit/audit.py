"""Offline documentation and Python AST inspection; source is never executed."""
import ast
import fnmatch
import os
import re
from pathlib import Path

from .phrases import TRACKING, NOTRACKING

CV = {
    'TrackerCSRT_create', 'TrackerKCF_create', 'TrackerMOSSE_create',
    'TrackerMIL_create', 'TrackerMedianFlow_create', 'TrackerTLD_create',
    'TrackerGOTURN_create', 'TrackerDaSiamRPN_create', 'TrackerNano_create',
    'TrackerVit_create', 'MultiTracker_create',
}


def prose(text):
    """Remove Markdown fenced blocks, preserving paragraph boundaries."""
    lines = []
    fence = None
    for line in text.splitlines():
        if fence:
            if re.match(r'^ {0,3}' + re.escape(fence[0]) + '{' + str(fence[1]) + r',}\s*$', line):
                fence = None
            lines.append('')
            continue
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if match and not (match[1][0] == '`' and '`' in match[2]):
            fence = (match[1][0], len(match[1]))
            lines.append('')
        else:
            lines.append(line)
    return '\n'.join(lines)


def claims(text):
    positive = negative = False
    for paragraph in re.split(r'\n\s*\n', prose(text)):
        paragraph = paragraph.lower().replace('’', "'").replace("n't", ' not').replace('-', ' ')
        paragraph = re.sub(r'\s+', ' ', paragraph)
        for phrase in sorted(NOTRACKING, key=len, reverse=True):
            pattern = r'\b' + re.escape(phrase) + r'\b'
            if re.search(pattern, paragraph):
                negative = True
                paragraph = re.sub(pattern, ' ', paragraph)
        for phrase in sorted(TRACKING, key=len, reverse=True):
            if re.search(r'\b' + re.escape(phrase) + r'\b', paragraph):
                positive = True
                break
    return positive, negative


def evidence(source):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    imports = {}
    shadowed = set()
    assignments = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = node.module + '.' + alias.name
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            shadowed.add(node.name)
        elif isinstance(node, ast.arg):
            shadowed.add(node.arg)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            assignments.append(node)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            shadowed.add(node.id)
    # Assignments invalidate imported providers, even if textually later.
    for name in shadowed:
        imports.pop(name, None)

    def resolve(node):
        if isinstance(node, ast.Name):
            return imports.get(node.id, '')
        if isinstance(node, ast.Attribute):
            parent = resolve(node.value)
            return parent + '.' + node.attr if parent else ''
        return ''

    def yolo(node):
        if not isinstance(node, ast.Call):
            return False
        path = resolve(node.func).split('.')
        return path[0] == 'ultralytics' and path[-1] == 'YOLO'

    models = set()
    writes = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            writes[node.id] = writes.get(node.id, 0) + 1
    for node in assignments:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and yolo(node.value) and writes.get(target.id) == 1:
                models.add(target.id)
    models -= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        path = resolve(node.func).split('.')
        provider, name = path[0], path[-1]
        if ((provider == 'cv2' and name in CV)
                or (provider == 'norfair' and name == 'Tracker')
                or (provider == 'supervision' and name == 'ByteTrack')
                or (provider in ('deep_sort', 'deep_sort_realtime') and name in ('DeepSort', 'DeepSORT'))
                or (provider == 'sort' and name == 'Sort')
                or (provider == 'dlib' and name == 'correlation_tracker')):
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'track':
            receiver = node.func.value
            if yolo(receiver) or (isinstance(receiver, ast.Name) and receiver.id in models):
                return True
    return False


def audit(root, ignore=(), fail_on='HIGH'):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError('root must be a readable directory')
    positive = negative = production = test = False
    count = 0

    def walk_error(error):
        raise error

    for directory, dirs, files in os.walk(str(root), followlinks=False, onerror=walk_error):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
        for filename in sorted(files):
            file = Path(directory) / filename
            relative = file.relative_to(root)
            path = relative.as_posix()
            if file.is_symlink() or any(fnmatch.fnmatchcase(path, pattern) for pattern in ignore):
                continue
            doc = path == 'README.md' or (file.suffix == '.md' and 'docs' in relative.parts[:-1])
            source = file.suffix == '.py'
            if not (doc or source):
                continue
            text = file.read_text(encoding='utf-8')
            count += 1
            if doc:
                yes, no = claims(text)
                positive |= yes
                negative |= no
            if source and not {'fixtures', 'docs', 'examples'}.intersection(relative.parts[:-1]):
                found = evidence(text)
                is_test = 'tests' in relative.parts[:-1] or filename.startswith('test_') or filename.endswith('_test.py')
                if is_test:
                    test |= found
                else:
                    production |= found
    findings = []
    if positive and not production:
        findings.append(dict(rule='documented-tracking-claim-false', severity='MEDIUM' if test else 'HIGH', message='Documentation promises cross-frame following without production provider evidence.'))
    if negative and production:
        findings.append(dict(rule='documented-no-tracking-claim-false', severity='HIGH', message='Documentation denies cross-frame following but production provider evidence exists.'))
    failed = any(f['severity'] == 'HIGH' or fail_on == 'MEDIUM' for f in findings)
    return dict(verdict='FAIL' if failed else 'PASS', findings=findings, files_scanned=count)
