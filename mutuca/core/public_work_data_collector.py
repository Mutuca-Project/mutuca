"""
classe PublicWorksDataColector que deverá coletar os dados e retornálos simiestruturados em um arquivo JSON. Ela deve possuir as seguintes características:
   1. Servir como callback para a classe Request do scrapy.
   2. Realizar, portanto, as requisições para coletar os dados de cada seletor.
   3. Realizar a limpeza básica dos resultados obtidos.
   4. Adicionar métados importantes para avaliação de qualidade da extração dos dados, assimo como tratamento de erros robusto.
   5. Retornar um Scrapy Item na estrutura semiestruturada modelada.  
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from scrapy.http import Response

from mutuca.items.public_works_cityhall_items import CityHallPublicWorksItem
from mutuca.utils.logger import get_logger
from mutuca.utils.xpath_cleaner import XPathCleaner

logger = get_logger(__name__)


class PublicWorksDataCollector:
    """
    Coleta, limpa e estrutura os dados de obras públicas.

    Comportamentos principais:
    - Realiza a coleta de dados das múltiplas seções da página de informações de obras públicas
    - Limpa os resultados obtidos para padronização
    - Estrutura os dados em um formato JSON
    - Gera métricas de qualidade da extração

    """

    def __init__(self, selectors: Dict[str, Any]) -> None:
        """
        Inicializa o processo de coleta com os seletores Xpath

        Args:
            selectors (dict): Dicionário de seletores Xpath divididos por seção.

        Formato esperado:
           {
               "section_name": {
                   "categories": "xpath_para_categorias",
                   "values": "xpath_para_valores"
               },
               "simple_section": "xpath_simples"
           }
        """
        self.selectors = selectors
        self.cleaner = XPathCleaner()
        self.extraction_stats = {
            "total_sections": 0,
            "successful_sections": 0,
            "errors": [],
        }

    # TODO adicionar o tipo Response do scrapy
    def parse_public_work_data(self, response: Response, item_class) -> Any:
        """
        Callback principal para processar os dados de obras Públicas.

        Este método é projetado para ser utilizado diretamente como callback do Scrapy,
        extraindo todos os dados definidos nos seletores.

        Fluxo de execução:
        1. Reset de estatísticas
        2. Extração de todas as seções configuradas
        3. tratamento individual de erros por seção
        4. Geração de relatório de qualidade
        5. Convesão para Acrapy Item (se fornecido)

        Args:
            response (scrapy.http.Response): Objeto Response do Scrapy com a página carregada
            item_class (class, optional): Classe do Scrapy Item para retorno

        Returns:

            Item ou Dict: Scrapy Item se item_class fornecido, senão dict
        """

        logger.info("Iniciando extração de dados da obra", extra={"url": response.url})

        # Reset das estatísticas para cada execução
        self.extraction_stats = {
            "total_sections": 0,
            "successful_sections": 0,
            "errors": [],
        }

        extracted_data = {
            "url": response.url,
            "extraction_timestamp": datetime.now().isoformat(),
            "sections": {},
        }

        # Processar cada seção definida nos seletores
        for section_name, selectors_config in self.selectors.items():
            try:
                section_data = self._extract_section_data(
                    response, section_name, selectors_config
                )

                extracted_data["sections"][section_name] = section_data
                self.extraction_stats["successful_sections"] += 1

                logger.info(
                    f"Seção extraída com sucesso: {section_name}",
                    extra={
                        "section": section_name,
                        "extraction_method": section_data.get("extraction_method"),
                    },
                )

            except Exception as e:
                error_info = f"Erro na seção {section_name}: {str(e)}"
                self.extraction_stats["errors"].append(error_info)

                extracted_data["sections"][section_name] = {
                    "error": error_info,
                    "data": None,
                    "extraction_method": "failed",
                }

                logger.error(
                    f"Falha na extração da seção: {section_name}",
                    extra={"section": section_name, "error": str(e)},
                )

        # Adicionar o resumo da extração
        extracted_data["extracion_summary"] = self._generate_extraction_summary()

        logger.info(
            "Extração concluída com sucesso",
            extra={
                "success_rate": extracted_data["extracion_summary"]["success_rate"],
                "quality": extracted_data["extracion_summary"]["extraction_quality"],
            },
        )

        if item_class:
            return self.to_scrapy_item(extracted_data, item_class)

        return extracted_data

    def _generate_extraction_summary(self) -> Dict[str, Any]:
        """
        Gera resume estatístico da extração.

        Returns:
            dict: Resumo com estatísticas e classificação de qualidade da extração
        """
        sucess_rate = (
            (
                self.extraction_stats["successful_sections"]
                / self.extraction_stats["total_sections"]
            )
            if self.extraction_stats["total_sections"] > 0
            else 0
        )

        return {
            "total_sections_processed": self.extraction_stats["total_sections"],
            "successful_extractions": self.extraction_stats["successful_sections"],
            "failed_extractions": len(self.extraction_stats["errors"]),
            "success_rate": round(sucess_rate, 2),
            "extraction_quality": (
                "excelent"
                if sucess_rate >= 0.9
                else "good" if sucess_rate >= 0.7 else "needs_improvement"
            ),
            "errors": self.extraction_stats["errors"],
        }

    def _extract_section_data(
        self, response, section_name: str, config: Any
    ) -> Dict[str, Any]:
        """
        Extrai dados de uma seção específica baseada na configuração.

        Este método identifica automaticamente o tipo de extração necessária

        Tipos de extração suportados:
        - XPath simples (string direta com seletor XPath)
        - Dados pareados (dict com 'categories' e 'values')

        Args:
            response (scrapy.http.Response): Objeto Response do Scrapy
            section_name (str): Nome da seção sendo processada
            config (Any): Configuração dos seletores para cada seção

        Returns:
            dict: Dados estruturados da seção com metadados de extração

        Raises:
            ValueError: Se a configuração for inválida
        """

        # Caso especial: seção com xpath simples (exemplo: 'work_location')
        if isinstance(config, str):
            return self._extract_simple_xpath(response, config, section_name)

        # Caso padrão: seção com categories e values
        if isinstance(config, dict) and "categories" in config and "values" in config:
            return self._extract_paired_data(response, config, section_name)

        raise ValueError(f"Configuração inválida para seção {section_name}")

    def _extract_simple_xpath(
        self, response, xpath: str, section_name: str
    ) -> Dict[str, Any]:
        """
        Extrai dados usando um XPath simples.

        Este método é usado para seções que têm apenas um seletor XPath
        e não precisam de pareamento entre categorias e valores.

        Args:
            response (scrapy.http.Response): Objeto Response do Scrapy

        Returns:
            dict: Dados extraídos, limpos e com metados de qualidade
        """

        # Simulação da extração XPath (em ambiente real uar response.xpath())
        raw_values = self._execut_xpath_extraction(response, xpath)
        cleaned_values = self.cleaner.clean_html_text(raw_values)

        return {
            "extraction_method": "simple_xpath",
            "section_name": section_name,
            "xpath_used": xpath,
            "raw_count": len(raw_values),
            "cleaned_count": len(cleaned_values),
            "data_quality": self._assess_data_quality(raw_values, cleaned_values),
            "values": cleaned_values,
        }

    def _extract_paired_data(
        self, response, config: Dict[str, str], section_name: str
    ) -> Dict[str, Any]:
        """
        Extrai dados pareados (categorias e valores) usando XPath.

        Este método processa seções que têm tanto categorias quanto valores,
        criando um mapeamento estruturado entre eles. É a funcionalidade principal
        para a maioria das seções de obras públicas.

        Processo:
        1. Extração separada de categorias e valores
        2. Aplicação de limpeza em ambos os conjuntos
        3. Criação de mapeamento estruturado
        4. Geração de metadados de qualidade

        Args:
            response: (scrapy.http.Response): Objeto Response do scrapy
            config: (dict): Configuração com XPaths para 'categories' e 'values'
            section_name (str): Nome da seção

        Returns:
            Dados estruturados com categorias mapeadas para valores
        """

        # Simulação da extração de categorias
        raw_categories = self.self._execut_xpath_extraction(
            response, config["categories"]
        )
        cleaned_categories = self.cleaner.clean_html_text(raw_categories)

        # Extrair valores
        raw_values = self._execut_xpath_extraction(response, config["values"])
        cleaned_values = self._simulate_xpath_extration(raw_values, config["values"])

        # Cria o mapeamento estruturado
        structured_data = self._create_structured_mapping(
            cleaned_categories, cleaned_values
        )

        return {
            "extraction_method": "paired_data",
            "section_name": section_name,
            "xpaths_used": {
                "categories": config["categories"],
                "values": config["values"],
            },
            "categories_found": len(cleaned_categories),
            "values_found": len(cleaned_values),
            "mapping_successful": len(structured_data.get("paired_data", [])),
            "data_quality": {
                "categories": self._assess_data_quality(
                    raw_categories, cleaned_categories
                ),
                "values": self._assess_data_quality(raw_values, cleaned_values),
            },
            "raw_data": {"categories": cleaned_categories, "values": cleaned_values},
            "structured_data": structured_data,
        }

    def _create_structured_mapping(
        self, categories: List[str], values: List[str]
    ) -> Dict[str, Any]:
        """
        Cria mapeamento estruturado entre categorias e valores.

        Este método implementa a lógica de pareamento inteligente,
        lidando com casos onde o número de categorias e valores pode diferir.

        Estratégias de mapeamento:
        - Pareamento 1:1 quando possível
        - Identificação de valores não pareados
        - Cálculo de métricas de qualidade do pareamento

        Args:
            categories (Lis[str]): Lista de categorias limpas
            values (List[str]): Lista de valores limpos

        Returns:
            Mapeamento estruturado com métricas de qualidade
        """

        paired_data = []
        unpaired_values = []

        min_length = min(len(categories), len(values))
        for i in range(min_length):
            paired_data.append(
                {
                    "category": categories[i],
                    "value": values[i],
                    "pair_index": i,
                    "confidence": self._calculate_pairing_confidence(
                        categories[i], values[i]
                    ),
                }
            )

        # Capturar valores não pareados
        if len(values) > len(categories):
            unpaired_values = values[min_length:]

        pairing_quality = (
            "excellent"
            if min_length == len(values) == len(categories)
            else (
                "good"
                if min_length / max(len(values), len(categories), 1) > 0.8
                else "poor"
            )
        )

        return {
            "paired_data": paired_data,
            "pairing_quality": pairing_quality,
            "unpaired_values": unpaired_values,
            "paired_ratio": f"{min_length}/{len(values)}" if values else "0/0",
            "total_pairs": min_length,
        }

    def _calculate_pairing_confidence(self, category: str, value: str) -> str:
        """
        Calcula confiança do pareamento categoria-valor baseado em heurísticas.

        Args:
            category (str): Texto da categoria
            value (str): Texto do valor

        Returns:
            Nível de confiança: 'high', 'medium', 'low'
        """
        if not category or not value:
            return "low"

        # Heurísticas simples de validação
        if len(value.strip()) > 0 and len(category.strip()) > 0:
            return "high"

        return "medium"

    def _assess_data_quality(
        self, raw_data: List[str], cleaned_data: List[str]
    ) -> Dict[str, Any]:
        """
        Avalia a qualidade dos dados extraídos.

        Args:
            raw_data (List[str]): Dados brutos extraídos
            cleaned_values (List[list]): Dados após limpeza

        Returns:
            Métricas de qualidade dos dados

        """
        if not raw_data:
            return {"status": "no_data", "score": 0.0}

        cleaning_efficiency = len(cleaned_data) / len(raw_data) if raw_data else 0

        return {
            "status": "good" if cleaning_efficiency > 0.7 else "needs_review",
            "cleaning_efficiency": round(cleaning_efficiency, 2),
            "data_completeness": len(cleaned_data) > 0,
            "score": round(cleaning_efficiency, 2),
        }

    def _simulate_xpath_extration(self, response, xpath: str) -> List[str]:
        """
        Simula extração XPath para demonstração (em ambinete real usar response.xpath()).

        Args:
            response (MockResponse): Objeto Response 'mocado'
            xpath (str): Mock da expressão xpath

        Returns:
            Lista simulada de valores extraídos
        """

        # Simulação para fins de demonstração
        simulated_data = {
            "categories": ["Categoria 1", "Categoria 2", "<div>Categoria 3</div>"],
            "values": [
                "Valor A",
                "R$ 10.000,00",
                "<span>Dados importantes</span>",
                "\n  Valor final  \n",
            ],
        }

        if "card-title" in xpath:
            return simulated_data["categories"]
        elif "card-info" in xpath:
            return simulated_data["values"]
        else:
            return ["Dados simulados", "<p>HTML content</p>", "Informação adicional"]

    def export_to_json(
        self, data: Dict[str, Any], filename: Optional[str] = None
    ) -> str:
        """
        Exporta os dados extraídos para arquivo JSON

        Args:
            data (dict): Dados para exportar
            filename (str): Nome do arquivo (opcional, será gerado automaticamente se não for fornecido)

        Returns:
            Caminho do arquivo criado
        """
        if not filename:
            url_safe = re.sub(r"[^\w\-_.]", "_", data.get("url", "unknown"))[:30]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"public_work_data_{url_safe}_{timestamp}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return filename
