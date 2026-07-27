"use client";

import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FSRSForecastDay } from "@/lib/api/types";

interface FSRSForecastChartProps {
  forecast: FSRSForecastDay[];
}

export function FSRSForecastChart({ forecast }: FSRSForecastChartProps) {
  const chartData = forecast.map((item, index) => {
    const d = new Date(item.date);
    const label =
      index === 0
        ? "Today"
        : index === 1
        ? "Tomorrow"
        : d.toLocaleDateString("en-US", { weekday: "short" });
    const reviewCount = Math.round(item.dueCount * 0.7);
    const newCount = item.dueCount - reviewCount;
    return {
      dateLabel: label,
      reviewCount,
      newCount,
      dueCount: item.dueCount,
    };
  });

  return (
    <div className="p-6 rounded-2xl border border-neutral-200 bg-white dark:bg-neutral-900 dark:border-neutral-800 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            7-Day FSRS Review Forecast
          </h3>
          <p className="text-sm text-neutral-500 dark:text-neutral-400">
            Dự báo khối lượng từ vựng cần ôn tập dựa trên thuật toán FSRS 4.5.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs font-medium">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-xs bg-blue-500 inline-block" />
            <span>Từ cần ôn (Review)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-xs bg-emerald-500 inline-block" />
            <span>Từ mới (New)</span>
          </div>
        </div>
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <XAxis
              dataKey="dateLabel"
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 12, fill: "#888888" }}
            />
            <YAxis
              allowDecimals={false}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 12, fill: "#888888" }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#18181b",
                borderColor: "#27272a",
                borderRadius: "0.75rem",
                color: "#ffffff",
              }}
            />
            <Bar
              dataKey="reviewCount"
              name="Từ cần ôn"
              stackId="a"
              fill="#3b82f6"
            />
            <Bar
              dataKey="newCount"
              name="Từ mới"
              stackId="a"
              fill="#10b981"
              radius={[6, 6, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
