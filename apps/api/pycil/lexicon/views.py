"""Pure mappings from Lexi contracts to HTTP response models."""

from pycil.lexicon.contracts import SenseView
from pycil.lexicon.schemas import (
    SenseContent,
    SenseDetailRead,
    SenseFormRead,
    SenseReferenceRead,
    SenseRelationRead,
)


def sense_content(view: SenseView) -> SenseContent:
    return SenseContent(
        sense_id=view.sense_id,
        definition=view.definition,
        tier=view.tier,
        pos=view.pos,
        cefr_level=view.cefr_level,
        examples=view.examples,
        word=view.word,
        word_id=view.word_id,
    )


def sense_detail(view: SenseView, sense_id: int) -> SenseDetailRead:
    return SenseDetailRead(
        sense_id=sense_id,
        word=view.word,
        word_id=view.word_id,
        definition=view.definition,
        tier=view.tier,
        pos=view.pos,
        cefr_level=view.cefr_level,
        examples=list(view.examples),
        ipa_uk=view.ipa_uk,
        ipa_us=view.ipa_us,
        guideword=view.guideword,
        grammar=list(view.grammar),
        register=view.register,
        connotation=view.connotation,
        collocations=list(view.collocations),
        domain=view.domain,
        usage_note=view.usage_note,
        forms=[SenseFormRead(inf=form.inf, surface=form.surface) for form in view.forms],
        references=[
            SenseReferenceRead(source=reference.source, source_ref=reference.source_ref)
            for reference in view.references
        ],
        relations=[
            SenseRelationRead(
                rel_type=relation.rel_type,
                to_word_display=relation.to_word_display,
                to_word_id=relation.to_word_id,
                to_word_status=relation.to_word_status,
                wsd_state=relation.wsd_state,
                to_sense_id=relation.to_sense_id,
                to_sense_gloss=relation.to_sense_gloss,
            )
            for relation in view.relations
        ],
    )
