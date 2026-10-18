from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

PLUGIN=Path(__file__).resolve().parents[1]/'LightroomLocalDevelop.lrplugin'


class ResultDialogTests(unittest.TestCase):
    def runtime(self):
        lua=LuaRuntime(unpack_returned_tuples=True)
        lua.execute('''
        panels={};details={};nextAnswer='ok'
        factory={}
        function factory:control_spacing() return 8 end
        function factory:static_text(p) return p end
        function factory:separator(p) return p end
        function factory:column(p) return p end
        modules={LrView={osFactory=function() return factory end},LrDialogs={
          presentModalDialog=function(p)
            panels[#panels+1]=p
            local result=nextAnswer;nextAnswer='ok';return result
          end,
          message=function(t,b) details[#details+1]={t,b} end}}
        function import(n) return modules[n] end
        ''')
        return lua,lua.execute((PLUGIN/'ResultDialog.lua').read_text(encoding='utf-8'))

    def test_finished_counts_exclude_review_and_failures_without_adding_action_counts(self):
        lua,module=self.runtime()
        result=module.build(lua.table_from({'selected':15,'analysed':10,'autoChanged':8,'stableCurrent':2,
            'model':2,'policy':4,'review':1,'failed':1,'modified':3,'unreadable':1,'unverified':1}))
        self.assertEqual(result.completed,8)
        self.assertEqual(result.attention,4)
        self.assertEqual(result.completed+result.attention+3,15)
        self.assertIn('部分照片需查看',result.title)
        failed=module.build(lua.table_from({'selected':1,'analysed':1,'failed':1}))
        self.assertEqual(failed.completed,0)
        self.assertEqual(failed.attention,1)

    def test_primary_panel_is_short_and_details_are_on_demand(self):
        lua,module=self.runtime();g=lua.globals();g.nextAnswer='other'
        module.show(lua.table_from({'selected':1,'analysed':1,'autoChanged':1,'policy':1,
                                   'onlyUnmodified':True,'details':'private-folder / full technical report'}))
        self.assertEqual(len(g.panels),2)
        self.assertEqual(len(g.details),1)
        self.assertIn('private-folder',g.details[1][2])
        panel=g.panels[1]
        self.assertEqual(panel.actionVerb,'完成')
        self.assertEqual(panel.otherVerb,'查看詳細紀錄')
        titles=[row.title for row in panel.contents.values() if hasattr(row,'title') and row.title]
        self.assertIn('已完成 1 張照片',titles)
        self.assertIn('AI 本次未追加亮暗微調。',titles)
        self.assertFalse(any('private-folder' in title or '0 張' in title for title in titles))
        self.assertLessEqual(len(titles),6)

    def test_all_skipped_does_not_claim_completed_adjustments(self):
        lua,module=self.runtime()
        result=module.build(lua.table_from({'selected':5,'modified':5,'allSkipped':True,'onlyUnmodified':True}))
        self.assertEqual(result.completed,0)
        self.assertEqual(result.title,'沒有需要處理的照片')
        self.assertEqual(list(result.lines.values()),['略過已修改照片：5 張'])


if __name__=='__main__':unittest.main()
