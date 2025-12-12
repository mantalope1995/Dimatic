from typing import Dict, Any, Optional
from core.agentpress.task_plan import TaskPlan
from core.utils.logger import logger
from core.ai_models.registry import registry

class ModelRouter:
    """
    Selects the appropriate Qwen3-VL model variant based on conversation state.
    
    Qwen3-VL-Thinking: Used for initial planning and complex reasoning.
    Qwen3-VL-Instruct: Used for executing steps defined in the plan.
    """
    
    THINKING_MODEL = "Qwen/Qwen3-VL-235B-A22B-Thinking"
    INSTRUCT_MODEL = "Qwen/Qwen3-VL-235B-A22B-Instruct"
    
    def select_model(self, conversation_context: Dict[str, Any], requested_model: str = None) -> str:
        """
        Select appropriate model based on current phase.
        
        Args:
            conversation_context: Thread metadata containing active_task_plan
            requested_model: The model requested in config (default fallback)
            
        Returns:
            Model ID string for the selected variant
        """
        # Only route if the requested model is a Qwen family model or compatible
        if requested_model and "qwen" not in requested_model.lower() and "kortix" not in requested_model.lower():
            return requested_model
            
        # Check if there's an active task plan in the metadata
        active_plan_data = conversation_context.get("active_task_plan")
        
        if not active_plan_data:
            # No plan exists - default to Thinking model for new complex requests
            # Or if it's a simple chat, Thinking model is still good for general purpose
            logger.info("🧠 No active plan - Routing to Thinking model")
            return self.THINKING_MODEL
            
        try:
            # Parse the plan to check status
            plan = TaskPlan.from_dict(active_plan_data)
            
            if plan.status == "complete" or plan.status == "failed" or plan.status == "abandoned":
                # Plan is finished, treat as new request
                logger.info(f"🧠 Plan {plan.status} - Routing to Thinking model")
                return self.THINKING_MODEL
            
            # Plan is active and has remaining steps - execute with Instruct
            logger.info(f"⚡ Plan active (Step {plan.current_step_index + 1}/{len(plan.steps)}) - Routing to Instruct model")
            return self.INSTRUCT_MODEL
            
        except Exception as e:
            logger.error(f"Error parsing task plan in router: {e}")
            # Fallback to Thinking model if state is corrupt
            return self.THINKING_MODEL
