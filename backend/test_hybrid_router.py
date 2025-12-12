import unittest
import json
import re
from datetime import datetime
from core.agentpress.task_plan import TaskPlan, TaskStep
from core.agentpress.model_router import ModelRouter

class TestHybridRouter(unittest.TestCase):
    def setUp(self):
        self.router = ModelRouter()
        self.sample_plan_data = {
            "id": "plan-123",
            "original_request": "Build a website",
            "reasoning": "We need to do X and Y",
            "steps": [
                {
                    "id": "step-1",
                    "description": "Create index.html",
                    "status": "pending",
                    "tools_used": []
                },
                {
                    "id": "step-2",
                    "description": "Add styles",
                    "status": "pending",
                    "tools_used": []
                }
            ],
            "current_step_index": 0,
            "status": "active"
        }

    def test_task_plan_serialization(self):
        """Test TaskPlan from_dict and to_dict"""
        plan = TaskPlan.from_dict(self.sample_plan_data)
        self.assertEqual(plan.id, "plan-123")
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].description, "Create index.html")
        
        # Test serialization back
        serialized = plan.to_dict()
        self.assertEqual(serialized['id'], "plan-123")
        self.assertEqual(len(serialized['steps']), 2)
        
    def test_plan_progression(self):
        """Test marking steps as complete"""
        plan = TaskPlan.from_dict(self.sample_plan_data)
        
        # Advance step 1
        plan.mark_step_complete("Done")
        self.assertEqual(plan.steps[0].status, "complete")
        self.assertEqual(plan.steps[0].result, "Done")
        self.assertEqual(plan.current_step_index, 1)
        self.assertEqual(plan.status, "active")
        
        # Advance step 2 (last step)
        plan.mark_step_complete("Done too")
        self.assertEqual(plan.steps[1].status, "complete")
        self.assertEqual(plan.current_step_index, 1) # Stays at last index
        self.assertEqual(plan.status, "complete")
        
    def test_router_selection_no_plan(self):
        """Router should choose Thinking model if no active plan"""
        metadata = {}
        model = self.router.select_model(metadata, "kortix/basic")
        self.assertEqual(model, ModelRouter.THINKING_MODEL)
        
    def test_router_selection_active_plan(self):
        """Router should choose Instruct model if active plan exists"""
        metadata = {
            "active_task_plan": self.sample_plan_data
        }
        model = self.router.select_model(metadata, "kortix/basic")
        self.assertEqual(model, ModelRouter.INSTRUCT_MODEL)
        
    def test_router_selection_finished_plan(self):
        """Router should choose Thinking model if plan is complete"""
        finished_plan = self.sample_plan_data.copy()
        finished_plan["status"] = "complete"
        metadata = {
            "active_task_plan": finished_plan
        }
        model = self.router.select_model(metadata, "kortix/basic")
        self.assertEqual(model, ModelRouter.THINKING_MODEL)
        
    def test_plan_parsing_regex(self):
        """Test regex logic used in thread_manager"""
        content = """Here is the plan:
        <plan>
        {
            "id": "123",
            "reasoning": "Reason",
            "steps": []
        }
        </plan>
        End of plan.
        """
        match = re.search(r'<plan>(.*?)</plan>', content, re.DOTALL)
        self.assertTrue(match)
        json_str = match.group(1).strip()
        data = json.loads(json_str)
        self.assertEqual(data["id"], "123")
        
    def test_step_update_regex(self):
        """Test regex for step updates"""
        content = 'Some content... <step_update id="step-1" status="complete" result="Created file" />'
        match = re.search(r'<step_update\s+id="([^"]+)"\s+status="([^"]+)"\s+(?:result="([^"]*)")?.*?>', content)
        self.assertTrue(match)
        self.assertEqual(match.group(1), "step-1")
        self.assertEqual(match.group(2), "complete")
        self.assertEqual(match.group(3), "Created file")
        
if __name__ == '__main__':
    unittest.main()
