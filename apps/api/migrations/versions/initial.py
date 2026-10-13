"""Fresh application schema; native checkpoint DDL is owned by its driver."""

from alembic import op

revision = "initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE reference_words (
        id INTEGER NOT NULL,
        lemma TEXT NOT NULL,
        display_form TEXT NOT NULL,
        entry_type VARCHAR(12) NOT NULL,
        alternatives JSONB NOT NULL,
        inflections JSONB NOT NULL,
        CONSTRAINT pk_reference_words PRIMARY KEY (id),
        CONSTRAINT ck_reference_words_lemma_present CHECK (length(btrim(lemma)) > 0),
        CONSTRAINT ck_reference_words_display_present CHECK (length(btrim(display_form)) >
        0),
        CONSTRAINT ck_reference_words_search_surfaces CHECK (jsonb_typeof(alternatives) =
        'array' AND jsonb_typeof(inflections) = 'array' ),
        CONSTRAINT ck_reference_words_entrytype CHECK (entry_type IN ('word', 'phrasal_verb'
        , 'idiom' , 'phrase' , 'expression' ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE themes (
        id SERIAL NOT NULL,
        key VARCHAR(255) NOT NULL,
        name TEXT NOT NULL,
        voice TEXT NOT NULL,
        diction TEXT NOT NULL,
        CONSTRAINT pk_themes PRIMARY KEY (id),
        CONSTRAINT ck_themes_identity CHECK (id > 0 AND length(btrim(key)) > 0),
        CONSTRAINT uq_themes_key UNIQUE (key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE translations (
        id SERIAL NOT NULL,
        input_hash VARCHAR(64) NOT NULL,
        target_language VARCHAR(16) NOT NULL,
        content TEXT NOT NULL,
        CONSTRAINT pk_translations PRIMARY KEY (id),
        CONSTRAINT uq_translations_input_hash UNIQUE (input_hash, target_language)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE users (
        id UUID NOT NULL,
        clerk_subject VARCHAR(255) NOT NULL,
        display_name VARCHAR(255),
        handle VARCHAR(30),
        bio VARCHAR(500),
        plan VARCHAR(4) NOT NULL,
        settings JSONB DEFAULT '{}' ::jsonb NOT NULL,
        cycle_anchor TIMESTAMP WITH TIME ZONE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_users PRIMARY KEY (id),
        CONSTRAINT ck_users_settings_object CHECK (jsonb_typeof(settings) = 'object' ),
        CONSTRAINT ck_users_handle_shape CHECK (handle IS NULL OR handle ~
        '^[a-z][a-z0-9_]{2,29}$' ),
        CONSTRAINT ck_users_display_name_shape CHECK (display_name IS NULL OR (display_name
        = btrim(display_name) AND length(display_name) BETWEEN 1 AND 255)),
        CONSTRAINT uq_users_clerk_subject UNIQUE (clerk_subject),
        CONSTRAINT uq_users_handle UNIQUE (handle),
        CONSTRAINT ck_users_plan CHECK (plan IN ('free', 'pro' ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE words (
        id SERIAL NOT NULL,
        lemma TEXT NOT NULL,
        match_key VARCHAR(512) NOT NULL,
        entry_type VARCHAR(12),
        generation_state VARCHAR(7) NOT NULL,
        CONSTRAINT pk_words PRIMARY KEY (id),
        CONSTRAINT uq_words_match_key UNIQUE (match_key),
        CONSTRAINT ck_words_entrytype CHECK (entry_type IN ('word', 'phrasal_verb' , 'idiom'
        , 'phrase' , 'expression' )),
        CONSTRAINT ck_words_generationstate CHECK (generation_state IN ('pending', 'done' ,
        'error' ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE conversations (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        title VARCHAR(255),
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_conversations PRIMARY KEY (id),
        CONSTRAINT fk_conversations_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
        ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE nodes (
        id UUID NOT NULL,
        owner_id UUID NOT NULL,
        type VARCHAR(9) NOT NULL,
        parent_id UUID,
        reference_id UUID,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        search_vector TSVECTOR GENERATED ALWAYS AS
        (setweight(to_tsvector('simple'::regconfig, coalesce(name, '' )), 'A' ) ||
        setweight(to_tsvector('simple'::regconfig, coalesce(description, '' )), 'B' ))
        STORED NOT NULL,
        role VARCHAR(14) NOT NULL,
        space VARCHAR(9) NOT NULL,
        deleted_at TIMESTAMP WITH TIME ZONE,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_nodes PRIMARY KEY (id),
        CONSTRAINT ck_nodes_not_own_parent CHECK (parent_id IS NULL OR parent_id != id),
        CONSTRAINT ck_nodes_not_own_reference CHECK (reference_id IS NULL OR reference_id !=
        id),
        CONSTRAINT ck_nodes_reference_shape CHECK ((type = 'reference' ) = (reference_id IS
        NOT NULL)),
        CONSTRAINT ck_nodes_root_shape CHECK ((role = 'library_root' ) = (parent_id IS
        NULL)),
        CONSTRAINT ck_nodes_system_folder CHECK (role = 'normal' OR type = 'folder' ),
        CONSTRAINT uq_nodes_owner_id UNIQUE (owner_id, id),
        CONSTRAINT fk_nodes_owner_id_nodes FOREIGN KEY(owner_id, parent_id) REFERENCES nodes
        (owner_id, id) ON DELETE CASCADE,
        CONSTRAINT fk_nodes_owner_id_users FOREIGN KEY(owner_id) REFERENCES users (id) ON
        DELETE CASCADE,
        CONSTRAINT ck_nodes_nodetype CHECK (type IN ('folder', 'deck' , 'reference' )),
        CONSTRAINT fk_nodes_reference_id_nodes FOREIGN KEY(reference_id) REFERENCES nodes
        (id) ON DELETE CASCADE,
        CONSTRAINT ck_nodes_noderole CHECK (role IN ('normal', 'library_root' ,
        'personal_root' , 'published_root' )),
        CONSTRAINT ck_nodes_nodespace CHECK (space IN ('library', 'personal' , 'published'
        ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE reference_senses (
        id INTEGER NOT NULL,
        word_id INTEGER NOT NULL,
        definition TEXT NOT NULL,
        pos TEXT,
        headword TEXT,
        phrase_title TEXT,
        ipa_uk TEXT,
        ipa_us TEXT,
        entry_order INTEGER NOT NULL,
        sense_order INTEGER NOT NULL,
        CONSTRAINT pk_reference_senses PRIMARY KEY (id),
        CONSTRAINT ck_reference_senses_definition_present CHECK (length(btrim(definition)) >
        0),
        CONSTRAINT ck_reference_senses_source_order CHECK (entry_order >= 0 AND sense_order
        >= 0),
        CONSTRAINT fk_reference_senses_word_id_reference_words FOREIGN KEY(word_id)
        REFERENCES reference_words (id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE review_log (
        user_id UUID NOT NULL,
        event_key UUID NOT NULL,
        request_hash TEXT NOT NULL,
        accepted_at TIMESTAMP WITH TIME ZONE NOT NULL,
        activity_day DATE NOT NULL,
        result JSONB NOT NULL,
        CONSTRAINT pk_review_log PRIMARY KEY (user_id, event_key),
        CONSTRAINT fk_review_log_user_id_users FOREIGN KEY(user_id) REFERENCES users (id) ON
        DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE senses (
        id SERIAL NOT NULL,
        word_id INTEGER NOT NULL,
        pos VARCHAR(12) NOT NULL,
        tier VARCHAR(11) NOT NULL,
        cefr_level VARCHAR(2),
        register VARCHAR(10),
        ipa_uk VARCHAR(80),
        ipa_us VARCHAR(80),
        CONSTRAINT pk_senses PRIMARY KEY (id),
        CONSTRAINT fk_senses_word_id_words FOREIGN KEY(word_id) REFERENCES words (id) ON
        DELETE CASCADE,
        CONSTRAINT ck_senses_partofspeech CHECK (pos IN ('noun', 'verb' , 'adjective' ,
        'adverb' , 'pronoun' , 'preposition' , 'conjunction' , 'determiner' , 'interjection'
        , 'numeral' , 'article' , 'auxiliary' )),
        CONSTRAINT ck_senses_tier CHECK (tier IN ('core', 'common' , 'less_common' , 'rare'
        )),
        CONSTRAINT ck_senses_cefrlevel CHECK (cefr_level IN ('a1', 'a2' , 'b1' , 'b2' , 'c1'
        , 'c2' )),
        CONSTRAINT ck_senses_register CHECK (register IN ('formal', 'informal' , 'slang' ,
        'literary' , 'specialist' ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE usage_periods (
        id UUID NOT NULL,
        user_id UUID NOT NULL,
        period_start TIMESTAMP WITH TIME ZONE NOT NULL,
        period_end TIMESTAMP WITH TIME ZONE NOT NULL,
        allowance_units BIGINT NOT NULL,
        used_units BIGINT NOT NULL,
        CONSTRAINT pk_usage_periods PRIMARY KEY (id),
        CONSTRAINT uq_usage_periods_user_id UNIQUE (user_id, period_start),
        CONSTRAINT ck_usage_periods_nonnegative_units CHECK (allowance_units >= 0 AND
        used_units >= 0),
        CONSTRAINT ck_usage_periods_valid_period CHECK (period_end > period_start),
        CONSTRAINT fk_usage_periods_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
        ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE user_daily_activity (
        user_id UUID NOT NULL,
        day DATE NOT NULL,
        applied_events INTEGER NOT NULL,
        practice_events INTEGER NOT NULL,
        CONSTRAINT pk_user_daily_activity PRIMARY KEY (user_id, day),
        CONSTRAINT ck_user_daily_activity_nonnegative_events CHECK (applied_events >= 0 AND
        practice_events >= 0),
        CONSTRAINT fk_user_daily_activity_user_id_users FOREIGN KEY(user_id) REFERENCES
        users (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE word_aliases (
        id SERIAL NOT NULL,
        word_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        match_key VARCHAR(512) NOT NULL,
        CONSTRAINT pk_word_aliases PRIMARY KEY (id),
        CONSTRAINT uq_word_aliases_word_id UNIQUE (word_id, match_key),
        CONSTRAINT fk_word_aliases_word_id_words FOREIGN KEY(word_id) REFERENCES words (id)
        ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE word_references (
        id SERIAL NOT NULL,
        word_id INTEGER NOT NULL,
        source_id INTEGER NOT NULL,
        CONSTRAINT pk_word_references PRIMARY KEY (id),
        CONSTRAINT fk_word_references_word_id_words FOREIGN KEY(word_id) REFERENCES words
        (id) ON DELETE CASCADE,
        CONSTRAINT uq_word_references_source_id UNIQUE (source_id),
        CONSTRAINT fk_word_references_source_id_reference_words FOREIGN KEY(source_id)
        REFERENCES reference_words (id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE word_relations (
        id SERIAL NOT NULL,
        from_word_id INTEGER NOT NULL,
        to_word_id INTEGER NOT NULL,
        rel_type VARCHAR(22) NOT NULL,
        CONSTRAINT pk_word_relations PRIMARY KEY (id),
        CONSTRAINT uq_word_relations_from_word_id UNIQUE (from_word_id, to_word_id,
        rel_type),
        CONSTRAINT fk_word_relations_from_word_id_words FOREIGN KEY(from_word_id) REFERENCES
        words (id) ON DELETE CASCADE,
        CONSTRAINT fk_word_relations_to_word_id_words FOREIGN KEY(to_word_id) REFERENCES
        words (id) ON DELETE CASCADE,
        CONSTRAINT ck_word_relations_wordrelationtype CHECK (rel_type IN ('word_family',
        'confused_with' , 'part_of_phrasal_family' ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE collocations (
        id SERIAL NOT NULL,
        sense_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        CONSTRAINT pk_collocations PRIMARY KEY (id),
        CONSTRAINT fk_collocations_sense_id_senses FOREIGN KEY(sense_id) REFERENCES senses
        (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE deck_senses (
        deck_id UUID NOT NULL,
        sense_id INTEGER NOT NULL,
        CONSTRAINT pk_deck_senses PRIMARY KEY (deck_id, sense_id),
        CONSTRAINT fk_deck_senses_deck_id_nodes FOREIGN KEY(deck_id) REFERENCES nodes (id)
        ON DELETE CASCADE,
        CONSTRAINT fk_deck_senses_sense_id_senses FOREIGN KEY(sense_id) REFERENCES senses
        (id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE definitions (
        id SERIAL NOT NULL,
        sense_id INTEGER NOT NULL,
        theme_id INTEGER,
        content TEXT NOT NULL,
        CONSTRAINT pk_definitions PRIMARY KEY (id),
        CONSTRAINT uq_definitions_sense_id UNIQUE (sense_id, theme_id),
        CONSTRAINT fk_definitions_sense_id_senses FOREIGN KEY(sense_id) REFERENCES senses
        (id) ON DELETE CASCADE,
        CONSTRAINT fk_definitions_theme_id_themes FOREIGN KEY(theme_id) REFERENCES themes
        (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE examples (
        id SERIAL NOT NULL,
        sense_id INTEGER NOT NULL,
        theme_id INTEGER,
        content TEXT NOT NULL,
        CONSTRAINT pk_examples PRIMARY KEY (id),
        CONSTRAINT fk_examples_sense_id_senses FOREIGN KEY(sense_id) REFERENCES senses (id)
        ON DELETE CASCADE,
        CONSTRAINT fk_examples_theme_id_themes FOREIGN KEY(theme_id) REFERENCES themes (id)
        ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE node_paths (
        ancestor_id UUID NOT NULL,
        descendant_id UUID NOT NULL,
        depth INTEGER NOT NULL,
        CONSTRAINT pk_node_paths PRIMARY KEY (ancestor_id, descendant_id),
        CONSTRAINT ck_node_paths_nonnegative_depth CHECK (depth >= 0),
        CONSTRAINT ck_node_paths_self_depth CHECK ((ancestor_id = descendant_id) = (depth =
        0)),
        CONSTRAINT fk_node_paths_ancestor_id_nodes FOREIGN KEY(ancestor_id) REFERENCES nodes
        (id) ON DELETE CASCADE,
        CONSTRAINT fk_node_paths_descendant_id_nodes FOREIGN KEY(descendant_id) REFERENCES
        nodes (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE question_artifacts (
        id SERIAL NOT NULL,
        sense_id INTEGER NOT NULL,
        theme_id INTEGER,
        artifact_type VARCHAR(20) NOT NULL,
        payload TEXT NOT NULL,
        payload_hash VARCHAR(64) NOT NULL,
        position INTEGER DEFAULT 0 NOT NULL,
        type_position INTEGER DEFAULT 0 NOT NULL,
        CONSTRAINT pk_question_artifacts PRIMARY KEY (id),
        CONSTRAINT ck_question_artifacts_positions CHECK (position >= 0 AND type_position >=
        0),
        CONSTRAINT fk_question_artifacts_sense_id_senses FOREIGN KEY(sense_id) REFERENCES
        senses (id) ON DELETE CASCADE,
        CONSTRAINT fk_question_artifacts_theme_id_themes FOREIGN KEY(theme_id) REFERENCES
        themes (id) ON DELETE CASCADE,
        CONSTRAINT ck_question_artifacts_questionartifacttype CHECK (artifact_type IN
        ('word_definition', 'word_to_usage' , 'context_word_meaning' , 'context_to_word' ,
        'dialogue_completion' , 'sentence_rewrite' ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE sense_forms (
        id SERIAL NOT NULL,
        sense_id INTEGER NOT NULL,
        surface TEXT NOT NULL,
        inf VARCHAR(15) NOT NULL,
        match_key VARCHAR(512) NOT NULL,
        head_key VARCHAR(512) NOT NULL,
        CONSTRAINT pk_sense_forms PRIMARY KEY (id),
        CONSTRAINT fk_sense_forms_sense_id_senses FOREIGN KEY(sense_id) REFERENCES senses
        (id) ON DELETE CASCADE,
        CONSTRAINT ck_sense_forms_inflection CHECK (inf IN ('base', 'past' ,
        'past_participle' , 'present_3sg' , 'ing' , 'plural' , 'comparative' , 'superlative'
        ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE sense_patterns (
        id SERIAL NOT NULL,
        sense_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        head_key VARCHAR(512),
        CONSTRAINT pk_sense_patterns PRIMARY KEY (id),
        CONSTRAINT fk_sense_patterns_sense_id_senses FOREIGN KEY(sense_id) REFERENCES senses
        (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE sense_references (
        id SERIAL NOT NULL,
        sense_id INTEGER NOT NULL,
        source VARCHAR(9) NOT NULL,
        source_ref VARCHAR(255) NOT NULL,
        CONSTRAINT pk_sense_references PRIMARY KEY (id),
        CONSTRAINT uq_sense_references_sense_id UNIQUE (sense_id, source, source_ref),
        CONSTRAINT fk_sense_references_sense_id_senses FOREIGN KEY(sense_id) REFERENCES
        senses (id) ON DELETE CASCADE,
        CONSTRAINT ck_sense_references_referencesource CHECK (source IN ('reference',
        'wordnet' ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE sense_relations (
        id SERIAL NOT NULL,
        from_sense_id INTEGER NOT NULL,
        to_word_id INTEGER NOT NULL,
        to_sense_id INTEGER,
        rel_type VARCHAR(8) NOT NULL,
        target_hash VARCHAR(64),
        resolve_attempted_at VARCHAR(32),
        CONSTRAINT pk_sense_relations PRIMARY KEY (id),
        CONSTRAINT uq_sense_relations_from_sense_id UNIQUE (from_sense_id, to_word_id,
        rel_type),
        CONSTRAINT fk_sense_relations_from_sense_id_senses FOREIGN KEY(from_sense_id)
        REFERENCES senses (id) ON DELETE CASCADE,
        CONSTRAINT fk_sense_relations_to_word_id_words FOREIGN KEY(to_word_id) REFERENCES
        words (id) ON DELETE CASCADE,
        CONSTRAINT fk_sense_relations_to_sense_id_senses FOREIGN KEY(to_sense_id) REFERENCES
        senses (id) ON DELETE SET NULL,
        CONSTRAINT ck_sense_relations_senserelationtype CHECK (rel_type IN ('synonym',
        'antonym' , 'hypernym' , 'hyponym' , 'meronym' , 'holonym' ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE usage_events (
        id UUID NOT NULL,
        period_id UUID NOT NULL,
        execution_key UUID NOT NULL,
        feature VARCHAR(16) NOT NULL,
        units BIGINT NOT NULL,
        unmetered_calls INTEGER NOT NULL,
        occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_usage_events PRIMARY KEY (id),
        CONSTRAINT ck_usage_events_nonnegative_units CHECK (units >= 0),
        CONSTRAINT fk_usage_events_period_id_usage_periods FOREIGN KEY(period_id) REFERENCES
        usage_periods (id) ON DELETE CASCADE,
        CONSTRAINT uq_usage_events_execution_key UNIQUE (execution_key),
        CONSTRAINT ck_usage_events_feature CHECK (feature IN ('assistant',
        'advanced_grading' ))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE user_senses (
        user_id UUID NOT NULL,
        sense_id INTEGER NOT NULL,
        stability DOUBLE PRECISION NOT NULL,
        difficulty DOUBLE PRECISION NOT NULL,
        last_exposure_at TIMESTAMP WITH TIME ZONE NOT NULL,
        due_at TIMESTAMP WITH TIME ZONE NOT NULL,
        elo DOUBLE PRECISION NOT NULL,
        review_count INTEGER NOT NULL,
        lapse_count INTEGER NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        CONSTRAINT pk_user_senses PRIMARY KEY (user_id, sense_id),
        CONSTRAINT ck_user_senses_positive_memory CHECK (stability > 0 AND difficulty > 0),
        CONSTRAINT ck_user_senses_valid_counts CHECK (review_count > 0 AND lapse_count >=
        0),
        CONSTRAINT fk_user_senses_user_id_users FOREIGN KEY(user_id) REFERENCES users (id)
        ON DELETE CASCADE,
        CONSTRAINT fk_user_senses_sense_id_senses FOREIGN KEY(sense_id) REFERENCES senses
        (id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_words_match_key_prefix ON words (match_key varchar_pattern_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_conversations_owner_updated ON conversations (user_id, updated_at,
        id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_owner_parent_order ON nodes (owner_id, parent_id, created_at,
        id) WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_parent_id ON nodes (parent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_published_order ON nodes (created_at, id) WHERE deleted_at IS
        NULL AND space = 'published' AND role = 'normal'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_published_owner_order ON nodes (owner_id, created_at, id)
        WHERE deleted_at IS NULL AND space = 'published' AND role = 'normal'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_reference_id ON nodes (reference_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_nodes_search_vector ON nodes USING gin (search_vector)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_nodes_owner_role ON nodes (owner_id, role) WHERE role !=
        'normal'
        """
    )
    op.execute(
        """
        CREATE INDEX ix_reference_senses_word_id ON reference_senses (word_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_senses_word_id ON senses (word_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_senses_word_pos_order ON senses (word_id, pos, id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_word_aliases_match_key ON word_aliases (match_key
        varchar_pattern_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_word_references_word_id ON word_references (word_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_word_relations_to_word_id ON word_relations (to_word_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_collocations_sense_id ON collocations (sense_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_deck_senses_sense_id ON deck_senses (sense_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_definitions_theme_id ON definitions (theme_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_definitions_neutral ON definitions (sense_id) WHERE theme_id
        IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_examples_scope ON examples (sense_id, theme_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_examples_theme_id ON examples (theme_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_node_paths_descendant ON node_paths (descendant_id, ancestor_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_question_artifacts_list_scope ON question_artifacts (sense_id,
        theme_id, id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_question_artifacts_scope ON question_artifacts (sense_id, theme_id,
        position)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_question_artifacts_theme_id ON question_artifacts (theme_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_question_artifacts_type_list_scope ON question_artifacts (sense_id,
        theme_id, artifact_type, id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_question_artifacts_type_scope ON question_artifacts (sense_id,
        theme_id, artifact_type, type_position)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_artifact_payload ON question_artifacts (sense_id,
        COALESCE(theme_id, 0), artifact_type, payload_hash)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_singleton_artifact ON question_artifacts (sense_id,
        COALESCE(theme_id, 0), artifact_type) WHERE artifact_type IN
        ('word_definition','word_to_usage')
        """
    )
    op.execute(
        """
        CREATE INDEX ix_sense_forms_head_key ON sense_forms (head_key)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_sense_forms_match_key ON sense_forms (match_key varchar_pattern_ops)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_sense_forms_sense_id ON sense_forms (sense_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_sense_patterns_head_key ON sense_patterns (head_key)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_sense_patterns_sense_id ON sense_patterns (sense_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_sense_references_sense_id ON sense_references (sense_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_sense_relations_target_pending ON sense_relations (to_word_id, id)
        WHERE resolve_attempted_at IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX ix_sense_relations_to_sense_id ON sense_relations (to_sense_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_sense_relations_to_word_id ON sense_relations (to_word_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_usage_events_period_id ON usage_events (period_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_user_senses_sense_id ON user_senses (sense_id)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_user_senses_user_due ON user_senses (user_id, due_at, sense_id)
        """
    )
    op.execute(
        """
        CREATE FUNCTION artifact_positions() RETURNS trigger
        LANGUAGE plpgsql SET search_path=public AS $$
        DECLARE old_scope boolean; new_position integer; new_type_position integer;
        BEGIN
        IF TG_WHEN='BEFORE' THEN
        IF TG_OP='DELETE' THEN
        PERFORM id FROM senses WHERE id=OLD.sense_id FOR UPDATE;
        RETURN OLD;
        END IF;
        IF TG_OP='UPDATE' AND ROW(OLD.sense_id,OLD.theme_id,OLD.artifact_type)
        IS NOT DISTINCT FROM ROW(NEW.sense_id,NEW.theme_id,NEW.artifact_type) THEN
        RETURN NEW;
        END IF;
        IF TG_OP='UPDATE' THEN
        PERFORM id FROM senses WHERE id IN (OLD.sense_id,NEW.sense_id) ORDER BY id FOR
        UPDATE;
        ELSE
        PERFORM id FROM senses WHERE id=NEW.sense_id FOR UPDATE;
        END IF;
        IF NEW.theme_id IS NULL THEN
        SELECT position INTO new_position FROM question_artifacts
        WHERE sense_id=NEW.sense_id AND theme_id IS NULL AND id<>NEW.id ORDER BY position
        DESC LIMIT 1;
        SELECT type_position INTO new_type_position FROM question_artifacts
        WHERE sense_id=NEW.sense_id AND theme_id IS NULL AND artifact_type=NEW.artifact_type
        AND id<>NEW.id ORDER BY type_position DESC LIMIT 1;
        ELSE
        SELECT position INTO new_position FROM question_artifacts
        WHERE sense_id=NEW.sense_id AND theme_id=NEW.theme_id AND id<>NEW.id ORDER BY
        position DESC LIMIT 1;
        SELECT type_position INTO new_type_position FROM question_artifacts
        WHERE sense_id=NEW.sense_id AND theme_id=NEW.theme_id AND
        artifact_type=NEW.artifact_type
        AND id<>NEW.id ORDER BY type_position DESC LIMIT 1;
        END IF;
        NEW.position:=COALESCE(new_position,0)+1;
        NEW.type_position:=COALESCE(new_type_position,0)+1;
        RETURN NEW;
        END IF;
        old_scope:=TG_OP='DELETE';
        IF TG_OP='UPDATE' THEN
        old_scope:=ROW(OLD.sense_id,OLD.theme_id,OLD.artifact_type)
        IS DISTINCT FROM ROW(NEW.sense_id,NEW.theme_id,NEW.artifact_type);
        END IF;
        IF old_scope THEN
        IF OLD.theme_id IS NULL THEN
        UPDATE question_artifacts SET position=OLD.position WHERE id=(
        SELECT id FROM question_artifacts WHERE sense_id=OLD.sense_id AND theme_id IS NULL
        AND position>OLD.position ORDER BY position DESC LIMIT 1);
        UPDATE question_artifacts SET type_position=OLD.type_position WHERE id=(
        SELECT id FROM question_artifacts WHERE sense_id=OLD.sense_id AND theme_id IS NULL
        AND artifact_type=OLD.artifact_type AND type_position>OLD.type_position
        ORDER BY type_position DESC LIMIT 1);
        ELSE
        UPDATE question_artifacts SET position=OLD.position WHERE id=(
        SELECT id FROM question_artifacts WHERE sense_id=OLD.sense_id AND
        theme_id=OLD.theme_id
        AND position>OLD.position ORDER BY position DESC LIMIT 1);
        UPDATE question_artifacts SET type_position=OLD.type_position WHERE id=(
        SELECT id FROM question_artifacts WHERE sense_id=OLD.sense_id AND
        theme_id=OLD.theme_id
        AND artifact_type=OLD.artifact_type AND type_position>OLD.type_position
        ORDER BY type_position DESC LIMIT 1);
        END IF;
        END IF;
        RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER artifact_positions_before BEFORE INSERT OR UPDATE OR DELETE ON
        question_artifacts FOR EACH ROW EXECUTE FUNCTION artifact_positions()
        """
    )
    op.execute(
        """
        CREATE TRIGGER artifact_positions_after AFTER UPDATE OR DELETE ON question_artifacts
        FOR EACH ROW EXECUTE FUNCTION artifact_positions()
        """
    )
    op.execute(
        """
        CREATE FUNCTION relation_definitions_insert() RETURNS trigger LANGUAGE plpgsql SET
        search_path=public AS $$
        DECLARE affected_senses integer[]; affected_words integer[];
        BEGIN
        WITH affected AS (SELECT r.sense_id AS id,s.word_id FROM new_rows r LEFT JOIN senses
        s ON s.id=r.sense_id WHERE r.theme_id IS NULL)
        SELECT array_agg(DISTINCT id),array_agg(DISTINCT word_id) INTO
        affected_senses,affected_words FROM affected;
        IF affected_senses IS NOT NULL THEN
        UPDATE sense_relations SET
        to_sense_id=NULL,target_hash=NULL,resolve_attempted_at=NULL
        WHERE from_sense_id=ANY(affected_senses) OR to_word_id=ANY(affected_words);
        END IF;
        RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER relation_definitions_insert AFTER INSERT ON definitions REFERENCING
        NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION
        relation_definitions_insert()
        """
    )
    op.execute(
        """
        CREATE FUNCTION relation_definitions_update() RETURNS trigger LANGUAGE plpgsql SET
        search_path=public AS $$
        DECLARE affected_senses integer[]; affected_words integer[];
        BEGIN
        WITH affected AS (SELECT r.sense_id AS id,s.word_id FROM old_rows r LEFT JOIN
        new_rows o ON o.id=r.id LEFT JOIN senses s ON s.id=r.sense_id WHERE r.theme_id IS
        NULL AND (o.id IS NULL OR ROW(r.theme_id,r.sense_id,r.content) IS DISTINCT FROM
        ROW(o.theme_id,o.sense_id,o.content)) UNION SELECT r.sense_id AS id,s.word_id FROM
        new_rows r LEFT JOIN old_rows o ON o.id=r.id LEFT JOIN senses s ON s.id=r.sense_id
        WHERE r.theme_id IS NULL AND (o.id IS NULL OR ROW(r.theme_id,r.sense_id,r.content)
        IS DISTINCT FROM ROW(o.theme_id,o.sense_id,o.content)))
        SELECT array_agg(DISTINCT id),array_agg(DISTINCT word_id) INTO
        affected_senses,affected_words FROM affected;
        IF affected_senses IS NOT NULL THEN
        UPDATE sense_relations SET
        to_sense_id=NULL,target_hash=NULL,resolve_attempted_at=NULL
        WHERE from_sense_id=ANY(affected_senses) OR to_word_id=ANY(affected_words);
        END IF;
        RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER relation_definitions_update AFTER UPDATE ON definitions REFERENCING
        OLD TABLE AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION
        relation_definitions_update()
        """
    )
    op.execute(
        """
        CREATE FUNCTION relation_definitions_delete() RETURNS trigger LANGUAGE plpgsql SET
        search_path=public AS $$
        DECLARE affected_senses integer[]; affected_words integer[];
        BEGIN
        WITH affected AS (SELECT r.sense_id AS id,s.word_id FROM old_rows r LEFT JOIN senses
        s ON s.id=r.sense_id WHERE r.theme_id IS NULL)
        SELECT array_agg(DISTINCT id),array_agg(DISTINCT word_id) INTO
        affected_senses,affected_words FROM affected;
        IF affected_senses IS NOT NULL THEN
        UPDATE sense_relations SET
        to_sense_id=NULL,target_hash=NULL,resolve_attempted_at=NULL
        WHERE from_sense_id=ANY(affected_senses) OR to_word_id=ANY(affected_words);
        END IF;
        RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER relation_definitions_delete AFTER DELETE ON definitions REFERENCING
        OLD TABLE AS old_rows FOR EACH STATEMENT EXECUTE FUNCTION
        relation_definitions_delete()
        """
    )
    op.execute(
        """
        CREATE FUNCTION relation_senses_insert() RETURNS trigger LANGUAGE plpgsql SET
        search_path=public AS $$
        DECLARE affected_senses integer[]; affected_words integer[];
        BEGIN
        WITH affected AS (SELECT r.id,r.word_id FROM new_rows r)
        SELECT array_agg(DISTINCT id),array_agg(DISTINCT word_id) INTO
        affected_senses,affected_words FROM affected;
        IF affected_senses IS NOT NULL THEN
        UPDATE sense_relations SET
        to_sense_id=NULL,target_hash=NULL,resolve_attempted_at=NULL
        WHERE from_sense_id=ANY(affected_senses) OR to_word_id=ANY(affected_words);
        END IF;
        RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER relation_senses_insert AFTER INSERT ON senses REFERENCING NEW TABLE
        AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION relation_senses_insert()
        """
    )
    op.execute(
        """
        CREATE FUNCTION relation_senses_update() RETURNS trigger LANGUAGE plpgsql SET
        search_path=public AS $$
        DECLARE affected_senses integer[]; affected_words integer[];
        BEGIN
        WITH affected AS (SELECT r.id,r.word_id FROM old_rows r LEFT JOIN new_rows o ON
        o.id=r.id WHERE (o.id IS NULL OR ROW(r.word_id,r.pos) IS DISTINCT FROM
        ROW(o.word_id,o.pos)) UNION SELECT r.id,r.word_id FROM new_rows r LEFT JOIN old_rows
        o ON o.id=r.id WHERE (o.id IS NULL OR ROW(r.word_id,r.pos) IS DISTINCT FROM
        ROW(o.word_id,o.pos)))
        SELECT array_agg(DISTINCT id),array_agg(DISTINCT word_id) INTO
        affected_senses,affected_words FROM affected;
        IF affected_senses IS NOT NULL THEN
        UPDATE sense_relations SET
        to_sense_id=NULL,target_hash=NULL,resolve_attempted_at=NULL
        WHERE from_sense_id=ANY(affected_senses) OR to_word_id=ANY(affected_words);
        END IF;
        RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER relation_senses_update AFTER UPDATE ON senses REFERENCING OLD TABLE
        AS old_rows NEW TABLE AS new_rows FOR EACH STATEMENT EXECUTE FUNCTION
        relation_senses_update()
        """
    )
    op.execute(
        """
        CREATE FUNCTION relation_senses_delete() RETURNS trigger LANGUAGE plpgsql SET
        search_path=public AS $$
        DECLARE affected_senses integer[]; affected_words integer[];
        BEGIN
        WITH affected AS (SELECT r.id,r.word_id FROM old_rows r)
        SELECT array_agg(DISTINCT id),array_agg(DISTINCT word_id) INTO
        affected_senses,affected_words FROM affected;
        IF affected_senses IS NOT NULL THEN
        UPDATE sense_relations SET
        to_sense_id=NULL,target_hash=NULL,resolve_attempted_at=NULL
        WHERE from_sense_id=ANY(affected_senses) OR to_word_id=ANY(affected_words);
        END IF;
        RETURN NULL;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER relation_senses_delete AFTER DELETE ON senses REFERENCING OLD TABLE
        AS old_rows FOR EACH STATEMENT EXECUTE FUNCTION relation_senses_delete()
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_sense_reference() RETURNS trigger
        LANGUAGE plpgsql SET search_path=public AS $$
        BEGIN
        IF NEW.source='reference' THEN
        IF NEW.source_ref !~ '^[1-9][0-9]{0,9}$' THEN
        RAISE EXCEPTION 'invalid reference citation' USING ERRCODE='23503';
        END IF;
        IF NOT EXISTS(
        SELECT 1 FROM reference_senses WHERE id=NEW.source_ref::bigint) THEN
        RAISE EXCEPTION 'invalid reference citation' USING ERRCODE='23503';
        END IF;
        END IF;
        RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER validate_sense_reference BEFORE INSERT OR UPDATE ON sense_references
        FOR EACH ROW EXECUTE FUNCTION validate_sense_reference()
        """
    )


def downgrade():
    op.execute(
        """
        DROP TABLE user_senses
        """
    )
    op.execute(
        """
        DROP TABLE usage_events
        """
    )
    op.execute(
        """
        DROP TABLE sense_relations
        """
    )
    op.execute(
        """
        DROP TABLE sense_references
        """
    )
    op.execute(
        """
        DROP TABLE sense_patterns
        """
    )
    op.execute(
        """
        DROP TABLE sense_forms
        """
    )
    op.execute(
        """
        DROP TABLE question_artifacts
        """
    )
    op.execute(
        """
        DROP TABLE node_paths
        """
    )
    op.execute(
        """
        DROP TABLE examples
        """
    )
    op.execute(
        """
        DROP TABLE definitions
        """
    )
    op.execute(
        """
        DROP TABLE deck_senses
        """
    )
    op.execute(
        """
        DROP TABLE collocations
        """
    )
    op.execute(
        """
        DROP TABLE word_relations
        """
    )
    op.execute(
        """
        DROP TABLE word_references
        """
    )
    op.execute(
        """
        DROP TABLE word_aliases
        """
    )
    op.execute(
        """
        DROP TABLE user_daily_activity
        """
    )
    op.execute(
        """
        DROP TABLE usage_periods
        """
    )
    op.execute(
        """
        DROP TABLE senses
        """
    )
    op.execute(
        """
        DROP TABLE review_log
        """
    )
    op.execute(
        """
        DROP TABLE reference_senses
        """
    )
    op.execute(
        """
        DROP TABLE nodes
        """
    )
    op.execute(
        """
        DROP TABLE conversations
        """
    )
    op.execute(
        """
        DROP TABLE words
        """
    )
    op.execute(
        """
        DROP TABLE users
        """
    )
    op.execute(
        """
        DROP TABLE translations
        """
    )
    op.execute(
        """
        DROP TABLE themes
        """
    )
    op.execute(
        """
        DROP TABLE reference_words
        """
    )
    op.execute(
        """
        DROP FUNCTION relation_definitions_insert()
        """
    )
    op.execute(
        """
        DROP FUNCTION relation_definitions_update()
        """
    )
    op.execute(
        """
        DROP FUNCTION relation_definitions_delete()
        """
    )
    op.execute(
        """
        DROP FUNCTION relation_senses_insert()
        """
    )
    op.execute(
        """
        DROP FUNCTION relation_senses_update()
        """
    )
    op.execute(
        """
        DROP FUNCTION relation_senses_delete()
        """
    )
    op.execute(
        """
        DROP FUNCTION artifact_positions()
        """
    )
    op.execute(
        """
        DROP FUNCTION validate_sense_reference()
        """
    )
