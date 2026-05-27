"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid
} from "recharts";

const AXIS = { stroke: "#5e6e82", fontSize: 11 };
const GRID = "#1f2937";
const TOOLTIP = {
  contentStyle: {
    background: "#0b1018",
    border: "1px solid #2c384a",
    borderRadius: 4,
    fontSize: 12,
    color: "#dbe1e8"
  },
  labelStyle: { color: "#8c9bad" },
  itemStyle: { color: "#f0a93b" }
};

interface BaseProps {
  height?: number;
  unit?: string;
}

interface LinePoint {
  ts: string;
  value: number;
}

interface LineProps extends BaseProps {
  type?: "line";
  data: LinePoint[];
  color?: string;
}

interface BarPoint {
  label: string;
  value: number;
}

interface BarProps extends BaseProps {
  type: "bar";
  data: BarPoint[];
  color?: string;
}

interface AreaProps extends BaseProps {
  type: "area";
  data: LinePoint[];
  color?: string;
}

type Props = LineProps | BarProps | AreaProps;

function formatTs(ts: string) {
  const d = new Date(ts);
  return Number.isNaN(d.getTime())
    ? ts
    : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function TrendChart(props: Props) {
  const height = props.height ?? 220;
  const color = (props as { color?: string }).color ?? "#f0a93b";
  const unit = props.unit ? ` ${props.unit}` : "";

  if (props.type === "bar") {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={props.data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="label" {...AXIS} />
          <YAxis {...AXIS} />
          <Tooltip
            {...TOOLTIP}
            formatter={(v: unknown) => [`${v}${unit}`, "Value"]}
          />
          <Bar dataKey="value" fill={color} radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (props.type === "area") {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={props.data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
          <defs>
            <linearGradient id="trend-area" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.45} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="ts" tickFormatter={formatTs} {...AXIS} />
          <YAxis {...AXIS} />
          <Tooltip
            {...TOOLTIP}
            labelFormatter={(l) => formatTs(String(l))}
            formatter={(v: unknown) => [`${v}${unit}`, "Value"]}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            fill="url(#trend-area)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  // default: line
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={props.data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="ts" tickFormatter={formatTs} {...AXIS} />
        <YAxis {...AXIS} />
        <Tooltip
          {...TOOLTIP}
          labelFormatter={(l) => formatTs(String(l))}
          formatter={(v: unknown) => [`${v}${unit}`, "Value"]}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
