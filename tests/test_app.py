"""Run: python -m unittest discover -s tests -v"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from domain import FIELDS, analyze, rating, level, clean_card, ValidationError

ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "data/demo.json").read_text(encoding="utf-8"))

class DomainTests(unittest.TestCase):
    def test_confirmation_and_weights(self):
        fields = DEMO["answers"]
        self.assertEqual(rating(fields, [])['score'], 0)
        result = rating(fields, list(FIELDS))
        self.assertEqual(result['score'], 100)
        self.assertEqual([g['maximum'] for g in result['groups']], [20,20,15,15,10,10,10])
        changed = dict(fields, data='')
        self.assertEqual(rating(changed, list(FIELDS))['score'], 80)
        self.assertEqual(rating(fields, [k for k in FIELDS if k != 'data'])['score'], 80)

    def test_levels_and_measurable_criteria(self):
        for score, key in [(0,'draft'),(39,'draft'),(40,'working'),(69,'working'),(70,'ready'),(89,'ready'),(90,'priority'),(100,'priority')]:
            self.assertEqual(level(score)['key'], key)
        self.assertEqual(rating(dict(DEMO['answers'], success='Жақсы жұмыс істеуі керек'), list(FIELDS))['score'], 85)

    def test_ai_grounded_minimum_questions(self):
        result = analyze({'description':DEMO['description'],'topic':'Сауда'})
        self.assertGreaterEqual(len(result['questions']),3)
        self.assertEqual(result['fields']['need'], DEMO['description'])
        self.assertEqual(result['fields']['data'],'')
        full = analyze({'description':DEMO['description'],'topic':'Сауда','answers':DEMO['answers']})
        self.assertEqual(full['fields'], DEMO['answers'])
        self.assertGreaterEqual(len(full['questions']),3)

    def test_ai_rejects_bad_json_hallucination_and_timeout(self):
        body={'description':DEMO['description'],'topic':'Сауда'}
        for raw in ['not-json','[]','{"fields":{"data":"Invented 500 clients"}}']:
            result=analyze(body, provider=lambda _:raw)
            self.assertTrue(result['warning'])
            self.assertEqual(result['fields']['data'],'')
        def broken(_): raise TimeoutError()
        self.assertTrue(analyze(body,provider=broken)['warning'])

    def test_card_validation(self):
        with self.assertRaises(ValidationError):
            clean_card({'fields':{},'topic':'Сауда'})
        with self.assertRaises(ValidationError):
            clean_card({'fields':DEMO['answers'],'topic':'Сауда','confirmed':[{}]})

    def test_seed_sizes_and_scores(self):
        seed=json.loads((ROOT/'data/seed.json').read_text(encoding='utf-8'))
        for key in ('drafts','cards','teams','proposals'):self.assertGreaterEqual(len(seed[key]),5)
        self.assertEqual([rating(t['fields'],t['confirmed'])['score'] for t in seed['cards']],[100,90,75,45,20])

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        server.DB_PATH=Path(self.tmp.name)/'test.sqlite3'
        os.environ['SANA_QUIET']='1'
        server.init_db()
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.base=f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.tmp.cleanup()

    def request(self,path,body=None,role='business',team='team_1',headers=None):
        h={'Content-Type':'application/json','X-Demo-Role':role,'X-Team-ID':team}
        h.update(headers or {})
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=h)
        try:
            with urlopen(req) as r:return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)

    def create(self,complete=True,publish=True):
        fields=dict(DEMO['answers']) if complete else {**{k:'' for k in FIELDS},'title':'Әлсіз бастапқы міндет','need':DEMO['description']}
        code,result=self.request('/api/tasks',{'fields':fields,'confirmed':list(FIELDS),'topic':'Сауда','publish':publish})
        self.assertEqual(code,200)
        return result['id']

    def proposal(self,task,team='team_1'):
        code,result=self.request('/api/proposals',{'task_id':task,**DEMO['proposal']},role='student',team=team)
        self.assertEqual(code,200)
        return result['id']

    def test_end_to_end_multiple_selection_and_points_once(self):
        task=self.create()
        p1=self.proposal(task)
        p2=self.proposal(task,'team_2')
        for p in (p1,p2):
            self.assertEqual(self.request('/api/proposals/'+p+'/decision',{'status':'accepted'})[0],200)
        self.assertEqual(self.request('/api/state')[1]['teams'][0]['points'],0)
        code,m=self.request('/api/milestones',{'proposal_id':p1,**DEMO['milestone']},role='student')
        self.assertEqual(code,200)
        path='/api/milestones/'+m['id']+'/review'
        self.assertEqual(self.request(path,{'decision':'approved'})[1]['points'],30)
        self.assertEqual(self.request(path,{'decision':'approved'})[0],409)
        self.assertEqual(self.request('/api/state')[1]['teams'][0]['points'],30)
        self.assertEqual(self.request('/api/proposals/'+p1+'/decision',{'status':'rejected'})[0],409)

    def test_low_score_not_hidden_or_blocked_unlimited_proposals(self):
        task=self.create(complete=False)
        _,s=self.request('/api/state',role='student',team='team_5')
        self.assertIn(task,[t['id'] for t in s['tasks']])
        self.assertLess(next(t for t in s['tasks'] if t['id']==task)['rating']['score'],40)
        for _ in range(7):self.proposal(task,'team_5')
        _,s=self.request('/api/state',role='student',team='team_5')
        self.assertEqual(len([p for p in s['proposals'] if p['task_id']==task]),7)

    def test_edit_recalculate_sort_revision_and_persistence(self):
        task=self.create(complete=False)
        code,_=self.request('/api/tasks/'+task,{'fields':DEMO['answers'],'topic':'Сауда','confirmed':list(FIELDS),'publish':True,'revision':1})
        self.assertEqual(code,200)
        self.assertEqual(self.request('/api/tasks/'+task,{'revision':1})[0],409)
        server.init_db() # Existing data must survive initialization/restart.
        _,s=self.request('/api/state')
        t=next(t for t in s['tasks'] if t['id']==task)
        self.assertEqual(t['rating']['score'],100)
        scores=[t['rating']['score'] for t in s['tasks']]
        self.assertEqual(scores,sorted(scores,reverse=True))

    def test_unpublished_hidden_and_cannot_receive_proposals(self):
        task=self.create(publish=False)
        self.assertNotIn(task,[t['id'] for t in self.request('/api/state',role='student')[1]['tasks']])
        self.assertEqual(self.request('/api/proposals',{'task_id':task,**DEMO['proposal']},role='student')[0],404)

    def test_publication_requires_confirmation_of_every_filled_field(self):
        body={'fields':DEMO['answers'],'topic':'Сауда','confirmed':['title'],'publish':True}
        self.assertEqual(self.request('/api/tasks',body)[0],400)
        body['publish']=False
        code,draft=self.request('/api/tasks',body)
        self.assertEqual(code,200)
        self.assertEqual(self.request('/api/tasks/'+draft['id'],{**body,'publish':True,'revision':1})[0],400)

    def test_role_ownership_and_no_automatic_assignment(self):
        p=self.proposal('task_agro')
        self.assertEqual(self.request('/api/proposals/'+p+'/decision',{'status':'accepted'},role='student')[0],403)
        self.assertEqual(self.request('/api/milestones',{'proposal_id':p,**DEMO['milestone']},role='student')[0],403)
        self.request('/api/proposals/'+p+'/decision',{'status':'accepted'})
        self.assertEqual(self.request('/api/milestones',{'proposal_id':p,**DEMO['milestone']},role='student',team='team_2')[0],403)
        self.assertTrue(all(x['team_id']=='team_2' for x in self.request('/api/state',role='student',team='team_2')[1]['proposals']))

    def test_revision_feedback_resubmit_and_reject(self):
        p=self.proposal('task_retail')
        self.request('/api/proposals/'+p+'/decision',{'status':'accepted'})
        m=self.request('/api/milestones',{'proposal_id':p,**DEMO['milestone']},role='student')[1]
        path='/api/milestones/'+m['id']+'/review'
        self.assertEqual(self.request(path,{'decision':'revision','feedback':'Толық мысал қосыңыз'})[0],200)
        self.assertEqual(self.request('/api/state')[1]['teams'][0]['points'],0)
        self.assertEqual(self.request('/api/milestones',{'proposal_id':p,**DEMO['milestone']},role='student')[0],200)
        self.assertEqual(self.request(path,{'decision':'approved'})[0],200)
        p2=self.proposal('task_retail','team_2')
        self.assertEqual(self.request('/api/proposals/'+p2+'/decision',{'status':'rejected'})[0],200)

    def test_invalid_input_url_origin_and_paths(self):
        self.assertEqual(self.request('/api/proposals',{'task_id':'task_agro',**DEMO['proposal'],'link':'javascript:alert(1)'},role='student')[0],400)
        self.assertEqual(self.request('/api/analyze',{'description':'x','topic':'Сауда'})[0],400)
        self.assertEqual(self.request('/api/analyze',{'description':DEMO['description'],'topic':'Сауда'},headers={'Origin':'https://untrusted.example'})[0],403)
        self.assertEqual(self.request('/data/sana.sqlite3')[0],404)

if __name__=='__main__':unittest.main()
