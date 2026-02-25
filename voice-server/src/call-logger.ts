import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, PutCommand } from '@aws-sdk/lib-dynamodb';

const dynamoClient = new DynamoDBClient({ region: process.env.DYNAMODB_REGION || 'us-east-1' });
const docClient = DynamoDBDocumentClient.from(dynamoClient);
const CALL_LOGS_TABLE = process.env.CALL_LOGS_TABLE || 'call-logs';

export interface CallLogEntry {
    callSid: string;
    timestamp: string;
    level: 'info' | 'warn' | 'error' | 'debug';
    event: string;
    message: string;
    metadata?: Record<string, any>;
}

/**
 * Write a log entry to DynamoDB
 */
export async function writeCallLog(entry: CallLogEntry): Promise<void> {
    try {
        const ttl = Math.floor(Date.now() / 1000) + (30 * 24 * 60 * 60); // 30 days TTL

        await docClient.send(new PutCommand({
            TableName: CALL_LOGS_TABLE,
            Item: {
                ...entry,
                ttl,
            },
        }));
    } catch (error) {
        console.error('Failed to write call log:', error);
        // Don't throw - logging should not break the call flow
    }
}

/**
 * Convenience functions for different log levels
 */
export const callLogger = {
    info(callSid: string, event: string, message: string, metadata?: Record<string, any>) {
        return writeCallLog({
            callSid,
            timestamp: new Date().toISOString(),
            level: 'info',
            event,
            message,
            metadata,
        });
    },

    warn(callSid: string, event: string, message: string, metadata?: Record<string, any>) {
        return writeCallLog({
            callSid,
            timestamp: new Date().toISOString(),
            level: 'warn',
            event,
            message,
            metadata,
        });
    },

    error(callSid: string, event: string, message: string, metadata?: Record<string, any>) {
        return writeCallLog({
            callSid,
            timestamp: new Date().toISOString(),
            level: 'error',
            event,
            message,
            metadata,
        });
    },

    debug(callSid: string, event: string, message: string, metadata?: Record<string, any>) {
        return writeCallLog({
            callSid,
            timestamp: new Date().toISOString(),
            level: 'debug',
            event,
            message,
            metadata,
        });
    },
};
