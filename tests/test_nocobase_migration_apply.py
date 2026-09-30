import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace


def database(path):
    content = b"%PDF-1.4\nmigration"
    digest = hashlib.sha256(content).hexdigest()
    db = sqlite3.connect(path)
    db.executescript("""
      CREATE TABLE candidates(id INTEGER PRIMARY KEY,archive_no TEXT,name TEXT,phone TEXT,resume TEXT);
      CREATE TABLE resume_documents(id INTEGER PRIMARY KEY,archive_no TEXT,source_id TEXT,file_hash TEXT,resume TEXT,status TEXT);
      CREATE TABLE attachments(id TEXT PRIMARY KEY,name TEXT,content BLOB);
      CREATE TABLE candidate_educations(id INTEGER PRIMARY KEY,candidate_id INTEGER,education TEXT,school_name TEXT,major TEXT);
      CREATE TABLE candidate_work_experiences(id INTEGER PRIMARY KEY,candidate_id INTEGER,organization TEXT);
      CREATE TABLE candidate_project_experiences(id INTEGER PRIMARY KEY,candidate_id INTEGER,project_name TEXT);
      CREATE TABLE resume_imports(source_id TEXT PRIMARY KEY,candidate_id INTEGER);
      CREATE TABLE applications(id INTEGER PRIMARY KEY,candidate_id INTEGER);
      CREATE TABLE interviews(id INTEGER PRIMARY KEY,candidate_id INTEGER);
      CREATE TABLE employees(id INTEGER PRIMARY KEY,candidate_id INTEGER);
    """)
    db.execute("INSERT INTO candidates VALUES(1,'C1','person','13900000001','A1')")
    db.execute("INSERT INTO resume_documents VALUES(2,'R1','S1',?,'A2','已识别')", (digest,))
    db.executemany("INSERT INTO attachments VALUES(?,?,?)", [('A1','a.pdf',content),('A2','b.pdf',content)])
    db.execute("INSERT INTO candidate_educations VALUES(1,1,'本科','大学','专业')")
    db.execute("INSERT INTO candidate_work_experiences VALUES(1,1,'单位')")
    db.execute("INSERT INTO candidate_project_experiences VALUES(1,1,'项目')")
    db.execute("INSERT INTO resume_imports VALUES('S1',1)")
    for table in ('applications','interviews','employees'): db.execute(f"INSERT INTO {table} VALUES(1,1)")
    db.commit(); db.close()


class Repo:
    def __init__(self, start): self.rows={}; self.next=start; self.calls=[]
    def create(self, values):
        identifier=self.next; self.next+=1; self.rows[identifier]=dict(values,id=identifier); self.calls.append(('create',identifier)); return identifier
    def update(self, identifier, values): self.rows[identifier].update(values); self.calls.append(('update',identifier))
    def delete(self, identifier): self.calls.append(('delete',identifier)); return self.rows.pop(identifier,None) is not None


class Relations:
    def __init__(self): self.rows={}; self.calls=[]
    def sync(self, identifier, kind, rows): self.rows[identifier,kind]=list(rows); self.calls.append((kind,identifier))


class Attachments:
    def __init__(self): self.rows={}; self.next=500
    def replace(self, identifier, upload, remove=False): self.rows[identifier]=dict(upload,id=self.next); self.next+=1
    def list(self, identifier): return [self.rows[identifier]] if identifier in self.rows else []
    def read(self, identifier): raise AssertionError('not used for empty target')
    def delete_if_unreferenced(self, identifier): return True


class CandidateService:
    def __init__(self): self.candidates=Repo(100); self.relations=Relations(); self.attachments=Attachments()
    def list_all(self, query=''): return [dict(row) for row in self.candidates.rows.values()]
    def get(self, identifier): return self.candidates.rows.get(identifier)
    def read_attachment(self, identifier): return self.attachments.read(identifier)
    def rollback_created(self, identifier): self.candidates.delete(identifier)


class ResumeService:
    def __init__(self): self.resumes=Repo(200); self.attachments=Attachments()
    def list_all(self, query=''): return [dict(row) for row in self.resumes.rows.values()]
    def get(self, identifier): return self.resumes.rows.get(identifier)
    def read_attachment(self, identifier): return self.attachments.read(identifier)
    def _cleanup_created(self, identifier): self.resumes.delete(identifier)


def services():
    return SimpleNamespace(candidates=CandidateService(), resumes=ResumeService(),
        preflight=SimpleNamespace(ok=True,resume_fields={'linked_candidate':'linked_candidate'}))


class MigrationApplyTests(unittest.TestCase):
    def test_latest_report_and_expiry(self):
        from features.nocobase_sync.migration_models import MigrationReport
        from features.nocobase_sync.migration_reports import save_report
        from features.nocobase_sync.migration_apply import select_latest_eligible_report
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); now=datetime(2026,1,2,12)
            old=MigrationReport(now-timedelta(hours=25),now-timedelta(hours=1),True,{}, {}, ())
            new=MigrationReport(now-timedelta(hours=1),now+timedelta(hours=23),True,{'x':1},{'x':'y'},())
            save_report(root,old); save_report(root,new)
            self.assertEqual(select_latest_eligible_report(root,now=lambda:now).counts,{'x':1})

    def test_six_stage_migration_journal_and_no_backend_change(self):
        from features.nocobase_sync.migration_reports import check_migration
        from features.nocobase_sync.migration_apply import apply_migration
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/'source.db'; database(path); api=services()
            report=check_migration(path,api)
            result=apply_migration(path,api,report,root/'journal.json')
            self.assertEqual(result.candidate_ids,{1:100}); self.assertEqual(result.resume_ids,{2:200})
            self.assertEqual(api.resumes.resumes.rows[200]['linked_candidate'],100)
            self.assertEqual({call[0] for call in api.candidates.relations.calls},{'education','work','project'})
            db=sqlite3.connect(path)
            self.assertEqual([db.execute(f'SELECT candidate_id FROM {t}').fetchone()[0] for t in ('applications','interviews','employees')],[100,100,100]); db.close()
            journal=json.loads((root/'journal.json').read_text(encoding='utf-8'))
            self.assertEqual(journal['stage'],'complete'); self.assertNotIn('person',(root/'journal.json').read_text(encoding='utf-8'))
            self.assertFalse((root/'recruitment-backend.json').exists())

    def test_changed_digest_stops_before_write_and_failure_cleans_up(self):
        from features.nocobase_sync.migration_reports import check_migration
        from features.nocobase_sync.migration_apply import apply_migration
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); path=root/'source.db'; database(path); api=services(); report=check_migration(path,api)
            db=sqlite3.connect(path); db.execute("UPDATE candidates SET archive_no='C2'"); db.commit(); db.close()
            with self.assertRaises(ValueError): apply_migration(path,api,report,root/'journal.json')
            self.assertEqual(api.candidates.candidates.rows,{})


if __name__ == '__main__': unittest.main()
