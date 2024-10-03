class PipelineFactory:
    def __init__(self):
        self._registry = {}

    def register_pipeline(self, spider_name, pipeline):
        """Registra um pipeline para uma spider específica."""
        self._registry[spider_name] = pipeline

    def get_pipelines(self, spider_name):
        """Retorna o pipeline registrado para a spider."""
        # Se não houver pipeline registrado, retorna uma pipeline padrão.
        return self._registry.get(
            spider_name,
            {
                "scrapy.pipelines.files.FilesPipeline": 1,
            },
        )
