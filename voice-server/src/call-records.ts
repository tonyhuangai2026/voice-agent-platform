import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import {
  DynamoDBDocumentClient,
  PutCommand,
  UpdateCommand,
  QueryCommand,
} from '@aws-sdk/lib-dynamodb';
import http from 'node:http';

export interface ActiveCall {
  callSid: string;
  streamSid: string;
  customerPhone: string;
  customerName: string;
  voiceId: string;
  startTime: string;
  turnCount: number;
  instanceId: string;
}

export interface TranscriptEntry {
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
}

export class CallRecordManager {
  private ddbDoc: DynamoDBDocumentClient;
  private tableName: string;
  private instanceId: string;

  constructor(tableName: string, region: string) {
    this.ddbDoc = DynamoDBDocumentClient.from(
      new DynamoDBClient({ region }),
      { marshallOptions: { removeUndefinedValues: true } }
    );
    this.tableName = tableName;
    this.instanceId = 'unknown';
    this.resolveInstanceId();
  }

  /** Resolve ECS task ID from container metadata endpoint */
  private async resolveInstanceId(): Promise<void> {
    const metadataUri = process.env.ECS_CONTAINER_METADATA_URI_V4;
    if (!metadataUri) {
      this.instanceId = `local-${process.pid}`;
      return;
    }
    try {
      const data = await new Promise<string>((resolve, reject) => {
        http.get(`${metadataUri}/task`, (res) => {
          let body = '';
          res.on('data', (chunk) => (body += chunk));
          res.on('end', () => resolve(body));
          res.on('error', reject);
        }).on('error', reject);
      });
      const meta = JSON.parse(data);
      // TaskARN format: arn:aws:ecs:region:account:task/cluster/taskId
      const taskArn: string = meta.TaskARN || '';
      this.instanceId = taskArn.split('/').pop() || `ecs-${process.pid}`;
    } catch {
      this.instanceId = `ecs-${process.pid}`;
    }
  }

  getInstanceId(): string {
    return this.instanceId;
  }

  /** Create a new call record when a call starts */
  async createRecord(
    callSid: string,
    streamSid: string,
    meta: { customerPhone: string; customerName: string; voiceId: string; projectId?: string }
  ): Promise<void> {
    try {
      const item: any = {
        callSid,
        streamSid,
        status: 'active',
        customerPhone: meta.customerPhone,
        customerName: meta.customerName,
        voiceId: meta.voiceId,
        startTime: new Date().toISOString(),
        transcript: [],
        turnCount: 0,
        instanceId: this.instanceId,
      };

      if (meta.projectId) {
        item.project_id = meta.projectId;
      }

      await this.ddbDoc.send(
        new PutCommand({
          TableName: this.tableName,
          Item: item,
        })
      );
      console.log(`[CallRecords] Created record for ${callSid} (project: ${meta.projectId || 'none'})`);
    } catch (err) {
      console.error(`[CallRecords] Error creating record for ${callSid}:`, err);
    }
  }

  /** Append a transcript entry to the call record */
  async appendTranscript(
    callSid: string,
    entry: { role: 'user' | 'assistant'; text: string }
  ): Promise<void> {
    try {
      const transcriptEntry: TranscriptEntry = {
        ...entry,
        timestamp: new Date().toISOString(),
      };
      await this.ddbDoc.send(
        new UpdateCommand({
          TableName: this.tableName,
          Key: { callSid },
          UpdateExpression:
            'SET transcript = list_append(if_not_exists(transcript, :empty), :entry) ADD turnCount :one',
          ExpressionAttributeValues: {
            ':entry': [transcriptEntry],
            ':empty': [],
            ':one': 1,
          },
        })
      );
    } catch (err) {
      console.error(`[CallRecords] Error appending transcript for ${callSid}:`, err);
    }
  }

  /** Mark a call as completed */
  async completeRecord(callSid: string, endReason: string, recordingS3Key?: string): Promise<void> {
    try {
      const endTime = new Date().toISOString();
      let updateExpr = 'SET #st = :completed, endTime = :endTime, endReason = :reason';
      const exprValues: Record<string, any> = {
        ':completed': 'completed',
        ':endTime': endTime,
        ':reason': endReason,
      };

      if (recordingS3Key) {
        updateExpr += ', recordingS3Key = :recKey';
        exprValues[':recKey'] = recordingS3Key;
      }

      await this.ddbDoc.send(
        new UpdateCommand({
          TableName: this.tableName,
          Key: { callSid },
          UpdateExpression: updateExpr,
          ExpressionAttributeNames: { '#st': 'status' },
          ExpressionAttributeValues: exprValues,
          ConditionExpression: 'attribute_exists(callSid)',
        })
      );
      console.log(`[CallRecords] Completed record for ${callSid}: ${endReason}${recordingS3Key ? ` (recording: ${recordingS3Key})` : ''}`);
    } catch (err) {
      console.error(`[CallRecords] Error completing record for ${callSid}:`, err);
    }
  }

  /** Query active calls for this instance */
  async getActiveCallsForInstance(): Promise<ActiveCall[]> {
    try {
      const result = await this.ddbDoc.send(
        new QueryCommand({
          TableName: this.tableName,
          IndexName: 'status-startTime-index',
          KeyConditionExpression: '#st = :active',
          FilterExpression: 'instanceId = :instId',
          ExpressionAttributeNames: { '#st': 'status' },
          ExpressionAttributeValues: {
            ':active': 'active',
            ':instId': this.instanceId,
          },
        })
      );
      return (result.Items || []).map((item) => ({
        callSid: item.callSid,
        streamSid: item.streamSid,
        customerPhone: item.customerPhone,
        customerName: item.customerName,
        voiceId: item.voiceId,
        startTime: item.startTime,
        turnCount: item.turnCount || 0,
        instanceId: item.instanceId,
      }));
    } catch (err) {
      console.error('[CallRecords] Error querying active calls:', err);
      return [];
    }
  }
}
