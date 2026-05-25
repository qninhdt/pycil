"use client";

import React, { useState, useMemo, useCallback, useRef, memo } from "react";
import { cn } from "@/lib";
import { Button } from "@/components/ui/button";
import {
  ChevronLeft,
  ChevronRight,
  Shuffle,
  RotateCcw,
  Maximize,
} from "lucide-react";
import { Swiper, SwiperSlide } from "swiper/react";
import { Navigation, Keyboard, Virtual } from "swiper/modules";

import type { Term } from "@/types/term";
import type { Swiper as SwiperType } from "swiper";
import { Flashcard } from ".";

// Import Swiper styles
import "swiper/css";
import "swiper/css/navigation";
import "swiper/css/virtual";

// FlashcardDeck component that manages the collection of flashcards with Swiper
interface FlashcardDeckProps {
  readonly terms: Term[];
  readonly className?: string;
}

export const FlashcardDeck = memo<FlashcardDeckProps>(
  ({ terms, className }) => {
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isShuffled, setIsShuffled] = useState(false);
    const swiperRef = useRef<SwiperType>(null);

    // Shuffle function to randomize the order of terms
    const shuffledTerms = useMemo(() => {
      if (!isShuffled) return terms;
      return [...terms].sort(() => Math.random() - 0.5);
    }, [terms, isShuffled]);

    const isFirstSlide = currentIndex === 0;
    const isLastSlide = currentIndex === shuffledTerms.length - 1;

    const handleNext = useCallback(() => {
      swiperRef.current?.slideNext();
    }, []);

    const handlePrevious = useCallback(() => {
      swiperRef.current?.slidePrev();
    }, []);

    const handleShuffle = useCallback(() => {
      setIsShuffled((prev) => !prev);
      setCurrentIndex(0);
      // Reset to first slide after shuffle
      setTimeout(() => {
        swiperRef.current?.slideTo(0, 0);
      }, 100);
    }, []);

    const handleReset = useCallback(() => {
      setCurrentIndex(0);
      setIsShuffled(false);
      swiperRef.current?.slideTo(0);
    }, []);

    const handleFullscreen = useCallback(() => {
      // Toggle fullscreen mode
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen();
      } else {
        document.exitFullscreen();
      }
    }, []);

    const onSlideChange = useCallback((swiper: SwiperType) => {
      setCurrentIndex(swiper.activeIndex);
    }, []);

    if (!shuffledTerms.length) {
      return (
        <div className="p-8 text-center rounded-xl border bg-card text-card-foreground shadow-sm">
          <h3 className="text-lg font-semibold mb-2">No terms available</h3>
          <p className="text-muted-foreground">
            Add some terms to start studying with flashcards.
          </p>
        </div>
      );
    }

    return (
      <div className={cn("space-y-6 flex flex-col", className)}>
        {/* Swiper Container */}
        <div className="flex-1">
          <Swiper
            modules={[Navigation, Keyboard, Virtual]}
            spaceBetween={50}
            slidesPerView={1}
            keyboard={{ enabled: true }}
            virtual={{
              enabled: true,
              addSlidesAfter: 2,
              addSlidesBefore: 2,
            }}
            onSwiper={(swiper) => {
              swiperRef.current = swiper;
            }}
            onSlideChange={onSlideChange}
            className="w-full h-full"
          >
            {shuffledTerms.map((term, index) => (
              <SwiperSlide
                key={`${term.id}-${isShuffled ? "shuffled" : "normal"}`}
                virtualIndex={index}
                className="w-full!"
              >
                <Flashcard
                  term={term}
                  className="h-full w-full"
                  // className="max-w-2xl aspect-[16/10] sm:aspect-[16/9] mx-auto"
                />
              </SwiperSlide>
            ))}
          </Swiper>
        </div>

        {/* Controls */}
        <div className="flex items-center justify-between w-full">
          {/* Left: Empty space */}
          <div className="flex-1"></div>

          {/* Center: [prev] [index] [next] */}
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="icon"
              onClick={handlePrevious}
              disabled={isFirstSlide}
              aria-label="Previous flashcard"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>

            <div
              className="text-sm text-foreground font-medium px-4"
              aria-label={`Flashcard ${currentIndex + 1} of ${
                shuffledTerms.length
              }`}
            >
              {currentIndex + 1} / {shuffledTerms.length}
            </div>

            <Button
              variant="outline"
              size="icon"
              onClick={handleNext}
              disabled={isLastSlide}
              aria-label="Next flashcard"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>

          {/* Right: [shuffle] [reset] [fullscreen] */}
          <div className="flex items-center gap-3 flex-1 justify-end">
            <Button
              variant="outline"
              size="icon"
              onClick={handleShuffle}
              aria-label={isShuffled ? "Unshuffle cards" : "Shuffle cards"}
              title={isShuffled ? "Unshuffle" : "Shuffle"}
            >
              <Shuffle className="h-4 w-4" />
            </Button>

            <Button
              variant="outline"
              size="icon"
              onClick={handleReset}
              aria-label="Reset to first card"
              title="Reset"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>

            <Button
              variant="outline"
              size="icon"
              onClick={handleFullscreen}
              aria-label="Toggle fullscreen"
              title="Fullscreen"
            >
              <Maximize className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    );
  }
);

FlashcardDeck.displayName = "FlashcardDeck";
