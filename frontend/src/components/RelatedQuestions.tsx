"use client";

import { motion } from "framer-motion";
import { ArrowRight, Microscope } from "lucide-react";

interface RelatedQuestionsProps {
  questions: string[];
  onSelect: (question: string) => void;
}

export default function RelatedQuestions({ questions, onSelect }: RelatedQuestionsProps) {
  if (!questions || questions.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, delay: 0.08 }}
      className="mt-3"
    >
      {/* Section label */}
      <div className="mb-2.5 flex items-center gap-1.5">
        <Microscope className="h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />
        <span className="text-[11px] font-medium uppercase tracking-widest text-slate-500 dark:text-slate-400">
          Explore further
        </span>
      </div>

      {/* Chip grid — horizontal wrap */}
      <motion.div
        variants={{
          hidden: {},
          show: { transition: { staggerChildren: 0.05 } },
        }}
        initial="hidden"
        animate="show"
        className="flex flex-wrap gap-2"
      >
        {questions.map((q, i) => (
          <motion.button
            key={i}
            variants={{
              hidden: { opacity: 0, scale: 0.92, y: 4 },
              show:   { opacity: 1, scale: 1,    y: 0, transition: { duration: 0.18 } },
            }}
            whileHover={{ scale: 1.04, y: -1 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => onSelect(q)}
            className="group flex cursor-pointer items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-xs text-slate-600 shadow-sm transition-all duration-150 hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 hover:shadow-md dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300 dark:hover:border-blue-600 dark:hover:bg-blue-950/40 dark:hover:text-blue-300"
          >
            <span className="leading-snug">{q}</span>
            <ArrowRight className="h-3 w-3 flex-shrink-0 opacity-0 transition-all duration-150 group-hover:translate-x-0.5 group-hover:opacity-60" />
          </motion.button>
        ))}
      </motion.div>

      <p className="mt-2.5 text-[10px] text-slate-300 dark:text-slate-600">
        Generated from evidence used in this answer
      </p>
    </motion.div>
  );
}
