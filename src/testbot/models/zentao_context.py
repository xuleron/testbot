"""禅道项目上下文。"""

from dataclasses import dataclass


@dataclass
class ProjectContext:
    """同步用例所需的禅道上下文。"""

    project_id: int
    product_id: int
    execution_id: int = 0
