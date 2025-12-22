import re
from typing import List


class XPathCleaner:
    """Utilitário para limpeza de dados extraídos via XPath"""

    @staticmethod
    # def clean_xpath_results(self, values: List[str]) -> List[str]:
    #     cleaned_values = []
    #     for item in values:
    #         # Remove tags <div> e </div>
    #         text = re.sub(r"<div[^>]*>", "", item)
    #         text = re.sub(r"</div>", "", text)
    #         # Remove quebras de linha e espaços extras
    #         text = text.replace("\n", "").strip()
    #         # Remove múltiplos espaços internos
    #         text = re.sub(r"\s+", " ", text)
    #         # Adiciona apenas se não for vazio
    #         if text:
    #             cleaned_values.append(text)

    #     return cleaned_values
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
