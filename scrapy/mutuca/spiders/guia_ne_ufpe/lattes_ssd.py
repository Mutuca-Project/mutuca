import io
import os
import re
import zipfile

from lxml import etree

import scrapy


class LattesSSDSpider(scrapy.Spider):
    name = "lattes_ssd"

    # Recebe os argumentos passados via linha de comando pelo Aiflow
    def __init__(
        self, offset=0, batch_size=100000, ssd_dir="/mnt/ssd_lattes", *args, **kwargs
    ):
        super(LattesSSDSpider, self).__init__(*args, **kwargs)
        self.offset = int(offset)
        self.batch_size = int(batch_size)
        self.ssd_dir = ssd_dir

        self.ne_states = {"AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"}
        self.status_pos = {"CONCLUIDO", "EM_ANDAMENTO"}

    def _clean_corrupted_caracters(self, text):
        """
        Resolve Mojibake, remove surrogates e limpa caracteres invisíveis para evitar
        perda de dados brutos .
        """
        if not isinstance(text, str):
            return text
        # Tenta corrigir o Mojibake (ex: revisÃ£o -> revisão)
        try:
            text = text.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Se falhar, o texto já está no encoding certo ou tem caracteres complexos. Segue o jogo.
            pass

        # Remove os surrogates: força a conversão segura
        try:
            text = text.encode("utf-8", "surrogatepass").decode("utf-8", "ignore")
        except Exception:
            pass

        # Regex para varrer qualquer resto de caracteres de controle
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1F\uD800-\uDFFF]", "", text)

        return text.strip()

    def _node_to_dict(self, node):
        """
        Transforma um nó XML e seus filhos diretos em um dicionário para preservar todos
        os atributos (ex: TITULO, ANO, INSTITUICAO) sem precisar mapear um por um e limpandos
        caracteres inválidos.
        """

        data = {k: self._clean_corrupted_caracters(v) for k, v in node.attrib.items()}

        for child in node:
            # Algumas tags no Lattes têm sub-tags que precisam ser coletadas também.
            data[child.tag] = {
                k: self._clean_corrupted_caracters(v) for k, v in child.attrib.items()
            }
        return data

    def start_requests(self):
        """
        Lê o diretóriodo SSD, fatia a lista de arquivos com base no lote atual e
        gera as requisições locais (protocolo file://).
        """
        # Lista de todos os ZIPs e ordena para garantir a mesma sequência em todas as execuções
        files = [f for f in os.listdir(self.ssd_dir) if f.endswith(".zip")]
        files.sort()

        # Recorta apenas o lote que o Airflow mandar processar nesta DAG run
        batch = files[self.offset : self.offset + self.batch_size]

        self.logger.info(
            f"Iniciando lote: Offset {self.offset} | Total de arquivos: {len(batch)}"
        )

        for file in batch:
            absolute_path = os.path.join(self.ssd_dir, file)
            lattes_id = file.replace(".zip", "")

            local_url = f"file://{absolute_path}"

            yield scrapy.Request(
                url=local_url, callback=self.parse, cb_kwargs={"lattes_id": lattes_id}
            )

    def parse(self, response, lattes_id):
        """
        O response.body contém os bytes brutos do arquivo ZIP lido do SSD.
        Realiza a descompressão e o parsing em memória.
        """

        try:
            # Transforma os bytes em um arquivo em memória para o zipfile ler
            with zipfile.ZipFile(io.BytesIO(response.body)) as zf:
                zip_internal_path = f"{lattes_id}.xml"

                with zf.open(zip_internal_path) as xml_file:
                    xml_bytes = xml_file.read()

                    root = etree.fromstring(xml_bytes)

                    # 1. Filtro de Endereço (Nordeste) - Fail-fast
                    address = root.find(".//ENDERECO-PROFISSIONAL")
                    if address is None or address.get("UF") not in self.ne_states:
                        return  # Ignora o perfil (não dá yield)

                    # 2. Filtro de Pós-graduação
                    tags_pos = root.xpath(
                        ".//MESTRADO | .//DOUTORADO | .//POS-DOUTORADO"
                    )
                    eh_pos = any(
                        tag.get("STATUS-DO-CURSO") in self.status_pos
                        for tag in tags_pos
                    )

                    if not eh_pos:
                        return

                    # 3. Extração dos dados úteis
                    general_data = root.find(".//DADOS-GERAIS")
                    name = (
                        general_data.get("NOME-COMPLETO")
                        if general_data is not None
                        else "N/A"
                    )
                    performances = [
                        self._node_to_dict(n)
                        for n in root.xpath(".//ATUACAO-PROFISSIONAL")
                    ]
                    projects = [
                        self._node_to_dict(n)
                        for n in root.xpath(".//PROJETO-DE-PESQUISA")
                    ]
                    production = [
                        self._node_to_dict(n) for n in root.xpath(".//ARTIGO-PUBLICADO")
                    ]

                    # TODO - Usar um Scrapy Item formal aqui (o dicionário é para teste)
                    yield {
                        "id_lattes": lattes_id,
                        "nome": self._clean_corrupted_caracters(name),
                        "uf_atuacao": self._clean_corrupted_caracters(
                            address.get("UF")
                        ),
                        "profetional_performances": performances,
                        "research_projects": projects,
                        "bibliographic_productions": production,
                    }

        except Exception as e:
            self.logger.error(f"Erro ao processar o ZIP {lattes_id}: {str(e)}")
