from mutuca.pipelines.pipeline_factory import PipelineFactory


class PipelineBuilder:
    def __init__(self):
        self.factory = PipelineFactory()

        # Registra a pipeline para uma spider específica 
        self.factory.register_pipeline(
            "parliamentary_allowance",
            {
                "mutuca.pipelines.parliamentary_allowance_pipelines.GoogleDriveLoadPDF": 1
            },
        )

    def get_pipelines(self, spider_name):
        # Usa a fábrica para obter o pipeline da spider
        return self.factory.get_pipelines(spider_name)
