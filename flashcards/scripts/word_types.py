#!/usr/bin/env python3
"""
Word type definitions for German vocabulary cards.
All word types must match these exact values (case-sensitive).
"""

from enum import Enum

class WordType(Enum):
    """
    Valid word types for German vocabulary cards.

    IMPORTANT: Case-sensitive! Must match exactly.
    - ✅ "Noun"
    - ❌ "noun", "NOUN", "Noun "
    """

    # Single word types
    NOUN = "Noun"
    VERB = "Verb"
    ADJECTIVE = "Adjective"
    ADVERB = "Adverb"
    PREPOSITION = "Preposition"
    CONJUNCTION = "Conjunction"
    ARTICLE = "Article"
    PRONOUN = "Pronoun"
    PARTICLE = "Particle"
    POSSESSIVE = "Possessive"
    QUESTION_WORD = "Question Word"

    # Compound types (words functioning as multiple types)
    # Note: Use alphabetical order for consistency
    ADJECTIVE_ADVERB = "Adjective/Adverb"
    ADVERB_PARTICLE = "Adverb/Particle"

    @classmethod
    def all_values(cls):
        """Get all valid word type strings."""
        return frozenset(wt.value for wt in cls)

    @classmethod
    def is_valid(cls, word_type_str):
        """
        Check if a string is a valid word type.
        Case-sensitive exact match required.

        Args:
            word_type_str: String to validate

        Returns:
            bool: True if valid or placeholder, False otherwise
        """
        # Allow empty or placeholder
        if not word_type_str or word_type_str.strip() == "—":
            return True

        # Must be exact match (case-sensitive)
        return word_type_str in cls.all_values()

    @classmethod
    def validate_strict(cls, word_type_str, context=""):
        """
        Validate word type with strict case-sensitive checking.
        Provides helpful error message for common mistakes.

        Args:
            word_type_str: The word type string to validate
            context: Optional context for error message

        Raises:
            ValueError: If word type is invalid, with specific guidance
        """
        # Skip validation for empty/placeholder
        if not word_type_str or word_type_str.strip() == "—":
            return

        # Exact match check
        if word_type_str in cls.all_values():
            return

        # Check for case mismatch
        word_type_lower = word_type_str.lower()
        for valid_type in cls.all_values():
            if valid_type.lower() == word_type_lower:
                raise ValueError(
                    f"Invalid word type: '{word_type_str}' {context}\n"
                    f"Case mismatch! Use exact capitalization: '{valid_type}'"
                )

        # Check for whitespace
        if word_type_str.strip() in cls.all_values():
            raise ValueError(
                f"Invalid word type: '{word_type_str}' {context}\n"
                f"Extra whitespace detected! Use: '{word_type_str.strip()}'"
            )

        # Not found at all
        valid_list = sorted(cls.all_values())
        raise ValueError(
            f"Invalid word type: '{word_type_str}' {context}\n"
            f"Must be one of: {', '.join(valid_list)}"
        )

    @classmethod
    def get_primary_type(cls, word_type_str):
        """
        Get the primary word type for categorization.
        For compound types like "Adjective/Adverb", returns "Adjective".

        Args:
            word_type_str: Word type string (must be valid)

        Returns:
            str or None: Primary type, or None if empty/placeholder
        """
        if not word_type_str or word_type_str.strip() == "—":
            return None

        # Validate before processing
        cls.validate_strict(word_type_str, "(in get_primary_type)")

        return word_type_str.split('/')[0]

    @classmethod
    def contains_type(cls, word_type_str, check_type_enum):
        """
        Check if word_type contains a specific type.
        For compound types like "Adjective/Adverb", checks both parts.

        Args:
            word_type_str: Word type string to check
            check_type_enum: WordType enum value to look for

        Returns:
            bool: True if word_type contains the check_type
        """
        if not word_type_str or word_type_str.strip() == "—":
            return False

        cls.validate_strict(word_type_str)

        parts = word_type_str.split('/')
        return check_type_enum.value in parts

    # Type checking methods (using exact matching)

    @classmethod
    def is_noun(cls, word_type_str):
        """Check if word type is exactly Noun."""
        return cls.get_primary_type(word_type_str) == cls.NOUN.value

    @classmethod
    def is_verb(cls, word_type_str):
        """Check if word type is exactly Verb."""
        return cls.get_primary_type(word_type_str) == cls.VERB.value

    @classmethod
    def is_adjective(cls, word_type_str):
        """Check if word type is or contains Adjective."""
        return cls.contains_type(word_type_str, cls.ADJECTIVE)

    @classmethod
    def is_adverb(cls, word_type_str):
        """Check if word type is or contains Adverb."""
        return cls.contains_type(word_type_str, cls.ADVERB)

    @classmethod
    def is_preposition(cls, word_type_str):
        """Check if word type is exactly Preposition."""
        return cls.get_primary_type(word_type_str) == cls.PREPOSITION.value

    @classmethod
    def is_article_conjunction_particle(cls, word_type_str):
        """Check if word type is Article, Conjunction, or Particle."""
        primary = cls.get_primary_type(word_type_str)
        return primary in {cls.ARTICLE.value, cls.CONJUNCTION.value, cls.PARTICLE.value}

    @classmethod
    def is_pronoun_possessive_question(cls, word_type_str):
        """Check if word type is Pronoun, Possessive, or Question Word."""
        primary = cls.get_primary_type(word_type_str)
        return primary in {cls.PRONOUN.value, cls.POSSESSIVE.value, cls.QUESTION_WORD.value}


def get_model_category(word_type_str):
    """
    Get the model category for deck generation.
    Maps word types to their card model.

    Args:
        word_type_str: Word type string (must be valid)

    Returns:
        str: Model category name for Anki deck generation
    """
    WordType.validate_strict(word_type_str, "(in get_model_category)")

    if WordType.is_noun(word_type_str):
        return "noun"
    elif WordType.is_verb(word_type_str):
        return "verb"
    elif WordType.is_adjective(word_type_str):
        return "adjective"
    elif WordType.is_preposition(word_type_str):
        return "preposition"
    elif WordType.is_adverb(word_type_str):
        return "adverb"
    elif WordType.is_article_conjunction_particle(word_type_str):
        return "basic"
    elif WordType.is_pronoun_possessive_question(word_type_str):
        return "pronoun"
    else:
        return "basic"  # Should never reach here if validation passed
