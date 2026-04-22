export const API_PREFIX = "/v1";

export const GAD7_LABELS = {
  "zh-CN": {
    Q1: "紧张、不安或易怒",
    Q2: "无法停止或控制担忧",
    Q3: "对各类事务过度担忧",
    Q4: "难以放松",
    Q5: "坐立不安",
    Q6: "易激惹或烦躁",
    Q7: "感到害怕",
  },
  "en-US": {
    Q1: "Nervous or on edge",
    Q2: "Unable to control worrying",
    Q3: "Worrying too much",
    Q4: "Trouble relaxing",
    Q5: "Restless",
    Q6: "Irritable",
    Q7: "Afraid something awful may happen",
  },
};

export const SEVERITY_TEXT = {
  "zh-CN": {
    minimal: "最小焦虑",
    mild: "轻度",
    moderate: "中度",
    severe: "重度",
  },
  "en-US": {
    minimal: "Minimal",
    mild: "Mild",
    moderate: "Moderate",
    severe: "Severe",
  },
};

export const GAD7_ORDER = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"];

export const LOCALES = ["zh-CN", "en-US"];
