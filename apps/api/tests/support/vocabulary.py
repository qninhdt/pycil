from pycil.vocabulary.enums import EntryType, GenerationState, PartOfSpeech, Tier
from pycil.vocabulary.models import Definition, Example, Sense, Word
from pycil.vocabulary.revisions import publish


async def neutral_word(sessions):
    async with sessions() as session, session.begin():
        word = Word(
            lemma="bank",
            match_key="bank",
            entry_type=EntryType.WORD,
            generation_state=GenerationState.DONE,
        )
        session.add(word)
        await session.flush()
        sense = Sense(word_id=word.id, pos=PartOfSpeech.NOUN, tier=Tier.CORE)
        session.add(sense)
        await session.flush()
        session.add(Definition(sense_id=sense.id, theme_id=None, content="a financial institution"))
        session.add(Example(sense_id=sense.id, theme_id=None, content="The [bank] opens at nine."))
        await publish(session, {word.id: None})
        return word.id, sense.id
