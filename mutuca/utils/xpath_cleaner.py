import re
from typing import List


class XPathCleaner:
    """Utilitário para limpeza de dados extraídos via XPath"""

    @staticmethod
    def clean_html_text(values: List[str]) -> List[str]:
        return [
            cleaned
            for item in values
            if (
                cleaned := re.sub(
                    r"\s+", " ", re.sub(r"<[^>]*>", "", item).replace("\n", "").strip()
                )
            )
        ]
