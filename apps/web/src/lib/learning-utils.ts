/**
 * Text-to-speech utility with proper error handling
 */
export const speakText = (text: string): Promise<void> => {
  return new Promise((resolve, reject) => {
    if (!("speechSynthesis" in window)) {
      reject(new Error("Speech synthesis not supported"));
      return;
    }

    try {
      // Cancel any ongoing speech
      speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);

      utterance.onend = () => resolve();
      utterance.onerror = (event) =>
        reject(new Error(`Speech synthesis error: ${event.error}`));

      // Set speech parameters
      utterance.rate = 0.8;
      utterance.pitch = 1;
      utterance.volume = 0.8;

      speechSynthesis.speak(utterance);
    } catch (error) {
      reject(error);
    }
  });
};

/**
 * Generate a hint for the correct answer
 */
export const generateHint = (answer: string): string => {
  if (!answer || answer.length === 0) return "";

  const cleanAnswer = answer.trim();
  const hintLength = Math.max(
    1,
    Math.min(3, Math.floor(cleanAnswer.length / 3))
  );

  return cleanAnswer.substring(0, hintLength) + "...";
};

/**
 * Normalize text for comparison (used in write questions)
 */
export const normalizeText = (text: string): string => {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s]/g, "")
    .replace(/\s+/g, " ");
};

/**
 * Check if two answers are equivalent
 */
export const areAnswersEquivalent = (
  userAnswer: string,
  correctAnswer: string
): boolean => {
  return normalizeText(userAnswer) === normalizeText(correctAnswer);
};

/**
 * Format time duration in a human-readable format
 */
export const formatDuration = (startTime: Date, endTime?: Date): string => {
  const end = endTime || new Date();
  const durationMs = end.getTime() - startTime.getTime();
  const durationSeconds = Math.floor(durationMs / 1000);

  if (durationSeconds < 60) {
    return `${durationSeconds}s`;
  }

  const minutes = Math.floor(durationSeconds / 60);
  const seconds = durationSeconds % 60;

  return `${minutes}m ${seconds}s`;
};

/**
 * Calculate accuracy percentage
 */
export const calculateAccuracy = (correct: number, total: number): number => {
  if (total === 0) return 0;
  return Math.round((correct / total) * 100);
};
