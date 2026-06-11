/** Queue configuration for BullMQ. */

interface QueueConfig {
  redisUrl: string;
  queueName: string;
  dlqName: string;
  defaultAttempts: number;
  defaultBackoffType: "fixed" | "exponential";
  defaultBackoffDelay: number;
  priority: {
    urgent: number;
    high: number;
    normal: number;
  };
}

function getEnv(key: string, defaultValue: string): string {
  if (typeof process !== "undefined" && process.env[key]) {
    return process.env[key]!;
  }
  return defaultValue;
}

export const queueConfig: QueueConfig = {
  redisUrl: getEnv("REDIS_URL", "redis://localhost:6379/0"),
  queueName: getEnv("QUEUE_NAME", "cv-generation"),
  dlqName: getEnv("DLQ_NAME", "cv-generation-dlq"),
  defaultAttempts: parseInt(getEnv("JOB_DEFAULT_ATTEMPTS", "3"), 10),
  defaultBackoffType: (getEnv("JOB_DEFAULT_BACKOFF_TYPE", "exponential") as "fixed" | "exponential"),
  defaultBackoffDelay: parseInt(getEnv("JOB_DEFAULT_BACKOFF_DELAY", "5000"), 10),
  priority: {
    urgent: parseInt(getEnv("PRIORITY_URGENT", "100"), 10),
    high: parseInt(getEnv("PRIORITY_HIGH", "50"), 10),
    normal: parseInt(getEnv("PRIORITY_NORMAL", "10"), 10),
  },
};

export type JobPriority = "urgent" | "high" | "normal";

export const PRIORITY_MAP: Record<JobPriority, number> = {
  urgent: queueConfig.priority.urgent,
  high: queueConfig.priority.high,
  normal: queueConfig.priority.normal,
};

export interface CVJobData {
  requestId: string;
  candidateFirstName?: string | null;
  instructions: string;
  priority: JobPriority;
  sourceFilePath: string;
  sourceFileName: string;
  sourceFileMime: string;
  sourceFileSize: number;
  createdBy: string;
  submittedAt?: string;
  enqueuedAt: string;
  attempt: number;
}

export interface DLQJobData {
  originalJob: CVJobData;
  failureReason: string;
  failureStacktrace: string[];
  attemptsMade: number;
  failedAt: string;
  workerName: string;
  errorType: string;
}