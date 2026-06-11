/** Queue producer for enqueueing CV generation jobs from the web app. */

import { Job } from "bullmq";
import { getMainQueue } from "./connection";
import { queueConfig, CVJobData, PRIORITY_MAP, JobPriority } from "./config";

const JOB_NAME = "cv-generation";

export interface EnqueueOptions {
  delay?: number;
  attempts?: number;
  backoffType?: "fixed" | "exponential";
  backoffDelay?: number;
}

class CVJobProducer {
  private _queue: ReturnType<typeof getMainQueue> | null = null;

  private get queue() {
    if (!this._queue) {
      this._queue = getMainQueue();
    }
    return this._queue;
  }

  async enqueue(jobData: CVJobData, options: EnqueueOptions = {}): Promise<Job> {
    const priority = PRIORITY_MAP[jobData.priority] ?? PRIORITY_MAP.normal;

    const jobOpts: Record<string, unknown> = {
      priority,
      attempts: options.attempts ?? queueConfig.defaultAttempts,
      backoff: {
        type: options.backoffType ?? queueConfig.defaultBackoffType,
        delay: options.backoffDelay ?? queueConfig.defaultBackoffDelay,
      },
      removeOnComplete: false,
      removeOnFail: false,
    };

    if (options.delay) {
      jobOpts.delay = options.delay;
    }

    const job = await this.queue.add(JOB_NAME, jobData, jobOpts);

    console.info(
      `[queue] Enqueued CV job request_id=${jobData.requestId} priority=${jobData.priority} job_id=${job.id}`,
    );

    return job;
  }

  async enqueueUrgent(jobData: CVJobData): Promise<Job> {
    jobData.priority = "urgent";
    return this.enqueue(jobData);
  }

  async enqueueHigh(jobData: CVJobData, delay = 0): Promise<Job> {
    jobData.priority = "high";
    return this.enqueue(jobData, delay > 0 ? { delay } : {});
  }

  async enqueueNormal(jobData: CVJobData, delay = 0): Promise<Job> {
    jobData.priority = "normal";
    return this.enqueue(jobData, delay > 0 ? { delay } : {});
  }

  async getQueueStats(): Promise<{
    waiting: number;
    active: number;
    completed: number;
    failed: number;
    delayed: number;
    total: number;
  }> {
    const [waiting, active, completed, failed, delayed] = await Promise.all([
      this.queue.getWaitingCount(),
      this.queue.getActiveCount(),
      this.queue.getCompletedCount(),
      this.queue.getFailedCount(),
      this.queue.getDelayedCount(),
    ]);

    return {
      waiting,
      active,
      completed,
      failed,
      delayed,
      total: waiting + active + completed + failed + delayed,
    };
  }

  async close(): Promise<void> {
    if (this._queue) {
      await this._queue.close();
      this._queue = null;
    }
  }
}

export const cvJobProducer = new CVJobProducer();

export async function createProducer(): Promise<CVJobProducer> {
  return cvJobProducer;
}