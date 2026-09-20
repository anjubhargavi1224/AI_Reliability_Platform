from ai_reliability.config import build_engine
from ai_reliability.experiments.models import Experiment, ExperimentRequest


def run_experiment(request: ExperimentRequest, config, store):
    engine = build_engine(config)
    experiment = Experiment(**request.model_dump(), configuration=config.model_copy(deep=True),
                            reports=[engine.evaluate(record) for record in request.records])
    store.save(experiment)
    return experiment
