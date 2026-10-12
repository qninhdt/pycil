"""Accepted diagnostic rubrics and one time-weighted Elo update per Sense."""

from statistics import mean

from lexi_ai import QuestionType, ResponseFormat


def evidence(item, target_sense_id):
    kind, fmt, d = item.question_type, item.format, item.diagnostics
    if fmt == ResponseFormat.SINGLE_CHOICE:
        score = float(d.correct)
        return target_sense_id, None if kind == QuestionType.WORD_TO_USAGE else score, score
    if fmt == ResponseFormat.SINGLE_WORD:
        if d.sense_id is not None and d.task_fit:
            return d.sense_id, 1.0, 0.8 if d.spelling_error else 1.0
        return target_sense_id, 0.0, 0.0
    if kind == QuestionType.WORD_TO_DEFINITION:
        if d.sense_id is not None and d.accuracy != "INACCURATE" and d.coverage != "MINIMAL":
            a = {"ACCURATE": 1.0, "MIXED": 0.5}[d.accuracy]
            c = {"SUFFICIENT": 1.0, "PARTIAL": 0.5}[d.coverage]
            return d.sense_id, 1.0, a * c
        return target_sense_id, 0.0, 0.0
    if not d.used:
        return (
            target_sense_id,
            (0.0 if kind == QuestionType.SENTENCE_REWRITE else None),
            (None if kind == QuestionType.SENTENCE_REWRITE else 0.0),
        )
    m = {"CORRECT": 1.0, "APPROXIMATE": 0.5, "WRONG": 0.0}[d.meaning]
    f = {"CORRECT": 1.0, "SPELLING_ERROR": 0.8, "FORM_ERROR": 0.5}[d.form]
    usage = m * mean([f, float(d.construction), float(d.collocation), float(d.appropriacy)])
    if kind == QuestionType.WORD_TO_USAGE:
        return target_sense_id, None, usage
    if m == 0:
        return target_sense_id, 0.0, None
    preservation = {"PRESERVED": 1.0, "PARTIAL": 0.5, "CHANGED": 0.0}[d.meaning_preservation]
    return target_sense_id, 1.0, usage * preservation


def update_elo(elo, performances, last_exposure_at, review_time, policy):
    observed = [(score, opponent) for score, opponent in performances if score is not None]
    if not observed:
        return elo
    weight = (
        min(
            1.0,
            max(
                0.0,
                (review_time - last_exposure_at).total_seconds() / (policy.horizon_hours * 3600),
            ),
        )
        if last_exposure_at
        else 1.0
    )
    residuals = []
    for score, opponent in observed:
        ratio = 10 ** (-abs((opponent - elo) / 400))
        expected = ratio / (1 + ratio) if opponent >= elo else 1 / (1 + ratio)
        residuals.append(score - expected)
    return elo + policy.k_elo * weight * mean(residuals)
