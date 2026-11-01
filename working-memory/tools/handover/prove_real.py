"""Generate five offline packages; console output contains numeric measurements only."""
import sys
sys.dont_write_bytecode = True
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import handover


def main():
    memory = handover.load_archive('auto')
    try:
        tasks = list(memory.tasks.values()) if isinstance(memory.tasks, dict) else memory.tasks
        candidates = sorted((t for t in tasks if t.get('status') == 'open'),
                            key=lambda t: (t.get('last_changed') or '', str(t.get('id', ''))),
                            reverse=True)
        selected, identities, themes = [], set(), set()
        # Prefer different themes; the mandate only requires distinct open IDs.
        for unique_theme in (True, False):
            for task in candidates:
                identity = task.get('id')
                theme = str(task.get('matter') or '').casefold()
                if not identity or identity in identities or (unique_theme and theme in themes):
                    continue
                selected.append(task); identities.add(identity); themes.add(theme)
                if len(selected) == 5: break
            if len(selected) == 5: break
        if len(selected) != 5: raise handover.HandoverError('E_FIVE_OPEN_TASKS')
        measurements = []
        for number, task in enumerate(selected, 1):
            package = handover.build_package(memory, task)
            text = handover.render_package(package)
            path = HERE / 'out' / f'paket-{number:02d}.md'
            handover.write_package(text, path)
            # Measure the actual saved bytes, not an estimated serialization.
            data = path.read_bytes()
            actual = data.decode('utf-8')
            if actual != text: raise handover.HandoverError('E_OUTPUT_MISMATCH')
            stats = handover.package_stats(package, actual)
            if (stats['bytes'] != len(data) or stats['bytes'] > 20_000 or
                    stats['zeilen'] > 150 or stats['laengste_zeile'] > 400):
                raise handover.HandoverError('E_OUTPUT_LIMIT')
            measurements.append({'paket': number, **stats})
        for measurement in measurements:
            print(json.dumps(measurement, ensure_ascii=False), flush=True)
    finally:
        if memory.db is not None: memory.db.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, handover.HandoverError) else 'E_PROOF', file=sys.stderr)
        raise SystemExit(2)
