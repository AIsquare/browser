"""
Run any SQL against corpus_v1.db.
  python q.py "SELECT ..."        # read
  python q.py --write "DELETE ..."  # write, commits
"""
import sqlite3
import sys

def main():
    args = sys.argv[1:]
    write = False
    if args and args[0] == '--write':
        write = True
        args = args[1:]
    if not args:
        print("usage: python q.py [--write] \"SQL\"")
        sys.exit(1)
    sql = ' '.join(args)

    conn = sqlite3.connect('corpus_v1.db')
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql)
        if cur.description:
            rows = cur.fetchall()
            if not rows:
                print("(no rows)")
            else:
                print(" | ".join(rows[0].keys()))
                print("-" * 60)
                for r in rows:
                    print(" | ".join(str(v)[:80] if v is not None else "-" for v in r))
        else:
            print(f"affected rows: {cur.rowcount}")
        if write:
            conn.commit()
            print("committed")
    except sqlite3.Error as e:
        print(f"error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    main()