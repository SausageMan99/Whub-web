/** Redis connection and BullMQ queue management for the web app. */

import { Queue, QueueEvents } from "bullmq";
import { queueConfig } from "./config";

let mainQueue: Queue | null = null;
let dlqQueue: Queue | null = null;
let queueEvents: QueueEvents | null = null;

interface RedisConnectionOpts {
  host: string;
  port: number;
  db: number;
  password?: string;
  maxRetriesPerRequest: number;
  retryStrategy: (times: number) => number | null;
  lazyConnect: boolean;
}

function getConnectionOpts(): { connection: RedisConnectionOpts } {
  const url = queueConfig.redisUrl;

  let host = "localhost";
  let port = 6379;
  let db = 0;
  let password: string | undefined;

  if (url.startsWith("redis://")) {
    const urlWithoutProtocol = url.slice(8);
    let authPart = "";
    let hostPortPart = urlWithoutProtocol;

    if (urlWithoutProtocol.includes("@")) {
      [authPart, hostPortPart] = urlWithoutProtocol.split("@");
      if (authPart.includes(":")) {
        password = authPart.split(":")[1];
      }
    }

    let hostPortDb = hostPortPart;
    if (hostPortDb.includes("/")) {
      const [hp, dbStr] = hostPortDb.split("/");
      hostPortDb = hp;
      db = parseInt(dbStr, 10);
    }

    if (hostPortDb.includes(":")) {
      const [hostPart, portPart] = hostPortDb.split(":");
      host = hostPart;
      port = parseInt(portPart, 10);
    } else {
      host = hostPortDb;
    }
  }

  return {
    connection: {
      host,
      port,
      db,
      ...(password ? { password } : {}),
      maxRetriesPerRequest: 3,
      retryStrategy: (times: number) => {
        if (times > 3) return null;
        return Math.min(times * 100, 3000);
      },
      lazyConnect: true,
    },
  };
}

export function getMainQueue(): Queue {
  if (!mainQueue) {
    mainQueue = new Queue(queueConfig.queueName, getConnectionOpts());
  }
  return mainQueue;
}

export function getDlqQueue(): Queue {
  if (!dlqQueue) {
    dlqQueue = new Queue(queueConfig.dlqName, getConnectionOpts());
  }
  return dlqQueue;
}

export function getQueueEvents(): QueueEvents {
  if (!queueEvents) {
    queueEvents = new QueueEvents(queueConfig.queueName, getConnectionOpts());
  }
  return queueEvents;
}

export async function closeQueueConnections(): Promise<void> {
  if (mainQueue) {
    await mainQueue.close();
    mainQueue = null;
  }
  if (dlqQueue) {
    await dlqQueue.close();
    dlqQueue = null;
  }
  if (queueEvents) {
    await queueEvents.close();
    queueEvents = null;
  }
}