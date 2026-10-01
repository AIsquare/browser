"""
Dump cached TypeSafe probabilities so we can see what we're actually
dealing with before choosing any thresholds.
"""
import json
from collections import Counter, defaultdict
from db import connect

conn = connect()


def histogram(values, buckets=10, width=10):
    """Print a text histogram of values in [0, 1]."""
    counts = [0] * buckets
    for v in values:
        idx = min(int(v * buckets), buckets - 1)
        counts[idx] += 1
    for i, c in enumerate(counts):
        lo = i / buckets
        hi = (i + 1) / buckets
        bar = '█' * min(c, 60)
        print(f"  [{lo:.1f}-{hi:.1f})  {c:5d}  {bar}")


# ----------------------------------------------------------------------
# SECTION ROLE decisions
# ----------------------------------------------------------------------

print("=" * 70)
print("SECTION ROLE CHOICE")
print("=" * 70)

rows = conn.execute(
    "SELECT answer FROM ts_cache WHERE kind='section'"
).fetchall()

role_counts = Counter()
confs = []
top_probs = []
p_margin = []

for r in rows:
    a = json.loads(r['answer'])
    role_counts[a['role']] += 1
    confs.append(a['role_conf'])

print(f"\nTop choice distribution ({len(rows)} sections):")
for role, n in role_counts.most_common():
    print(f"  {role:12s} {n:4d}")

print(f"\nConfidence histogram:")
histogram(confs)

# Noul distributions per question
print(f"\nNoul distributions (section level):")
for q in ['is_chrome', 'is_related', 'is_meta']:
    vals = []
    for r in rows:
        a = json.loads(r['answer'])
        if q in a:
            vals.append(a[q])
    if vals:
        print(f"\n  {q}:")
        histogram(vals)


# ----------------------------------------------------------------------
# ATOM quality decisions
# ----------------------------------------------------------------------

print()
print("=" * 70)
print("ATOM QUALITY")
print("=" * 70)

rows = conn.execute(
    "SELECT answer FROM ts_cache WHERE kind='atom'"
).fetchall()
print(f"\n{len(rows)} atom cache entries")

noul_qs = ['is_fragment', 'is_chrome_text', 'is_attribution',
           'is_label', 'is_caption']

data = defaultdict(list)
density_vals = []

for r in rows:
    a = json.loads(r['answer'])
    for q in noul_qs:
        if q in a:
            data[q].append(a[q])
    if 'density' in a:
        density_vals.append(a['density'])

for q in noul_qs:
    print(f"\n  {q}:")
    histogram(data[q])

print(f"\n  density (0-4):")
if density_vals:
    counts = [0] * 5
    for v in density_vals:
        idx = min(max(int(round(v)), 0), 4)
        counts[idx] += 1
    for i, c in enumerate(counts):
        bar = '█' * min(c, 60)
        print(f"  [{i}]    {c:5d}  {bar}")


# ----------------------------------------------------------------------
# DOC decisions
# ----------------------------------------------------------------------

print()
print("=" * 70)
print("DOCUMENT GATE")
print("=" * 70)

rows = conn.execute(
    "SELECT answer FROM ts_cache WHERE kind='doc'"
).fetchall()
print(f"\n{len(rows)} doc cache entries")
for r in rows:
    a = json.loads(r['answer'])
    print(f"  is_real={a['is_real']:.2f}  type={a['type']}")


# ----------------------------------------------------------------------
# How many atoms survive at various thresholds
# ----------------------------------------------------------------------

print()
print("=" * 70)
print("SURVIVAL AT DIFFERENT THRESHOLDS")
print("=" * 70)

print("\nIf is_fragment > X drops the atom:")
for x in [0.5, 0.6, 0.7, 0.8, 0.9]:
    n = sum(1 for v in data['is_fragment'] if v > x)
    print(f"  X={x}:  {n:4d} dropped")

print("\nIf is_caption > X drops the atom:")
for x in [0.5, 0.7, 0.8, 0.9]:
    n = sum(1 for v in data['is_caption'] if v > x)
    print(f"  X={x}:  {n:4d} dropped")

print("\nIf is_attribution > X drops the atom:")
for x in [0.5, 0.7, 0.8, 0.9]:
    n = sum(1 for v in data['is_attribution'] if v > x)
    print(f"  X={x}:  {n:4d} dropped")

print("\nIf ANY of (frag>0.7, chrome>0.6, attrib>0.8, label>0.7, "
      "caption>0.85) drops the atom:")
n = 0
for r in rows:
    a = json.loads(r['answer'])
    if (a.get('is_fragment', 0) > 0.7 or
        a.get('is_chrome_text', 0) > 0.6 or
        a.get('is_attribution', 0) > 0.8 or
        a.get('is_label', 0) > 0.7 or
        a.get('is_caption', 0) > 0.85 or
        a.get('density', 5) < 1.0):
        n += 1
print(f"  {n} dropped of {len(rows)}")

print("\nIf instead: frag>0.7 OR attrib>0.85 OR chrome>0.6 only:")
n = 0
for r in rows:
    a = json.loads(r['answer'])
    if (a.get('is_fragment', 0) > 0.7 or
        a.get('is_attribution', 0) > 0.85 or
        a.get('is_chrome_text', 0) > 0.6):
        n += 1
print(f"  {n} dropped of {len(rows)}")

conn.close()