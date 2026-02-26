import { useState, useEffect, useRef, useCallback } from 'react';
import { Card, Table, Typography, Tag, Space, Empty, Badge } from 'antd';
import { PhoneOutlined, MessageOutlined, ClockCircleOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { getActiveCalls, listCallRecords, createLiveTranscriptStream } from '../api';
import type { ActiveCall, DynamoCallRecord } from '../types';

const { Text } = Typography;

interface TranscriptMessage {
  role: string;
  content: string;
  timestamp?: string;
}

function formatDuration(startTime: string): string {
  const start = dayjs(startTime);
  const now = dayjs();
  const diffSec = now.diff(start, 'second');
  const mins = Math.floor(diffSec / 60);
  const secs = diffSec % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function LiveMonitor() {
  const [activeCalls, setActiveCalls] = useState<ActiveCall[]>([]);
  const [callRecords, setCallRecords] = useState<DynamoCallRecord[]>([]);
  const [selectedCall, setSelectedCall] = useState<ActiveCall | null>(null);
  const [transcriptMessages, setTranscriptMessages] = useState<TranscriptMessage[]>([]);
  const [, setTick] = useState(0);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Poll active calls every 3 seconds
  useEffect(() => {
    let mounted = true;

    const fetchActiveCalls = async () => {
      try {
        console.log('Fetching active calls...');
        const data = await getActiveCalls();
        console.log('Active calls received:', data);
        if (mounted) setActiveCalls(data.activeCalls);
      } catch (error) {
        console.error('Failed to fetch active calls:', error);
        // Voice server may not be reachable
      }
    };

    fetchActiveCalls();
    const interval = setInterval(fetchActiveCalls, 3000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Poll call records every 5 seconds
  useEffect(() => {
    let mounted = true;

    const fetchRecords = async () => {
      try {
        const data = await listCallRecords(20);
        if (mounted) setCallRecords(data.records);
      } catch (error) {
        console.error('Failed to fetch call records:', error);
        // API may not be reachable
      }
    };

    fetchRecords();
    const interval = setInterval(fetchRecords, 5000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Tick every second to update durations
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcriptMessages]);

  // Connect to SSE for live transcript
  const connectTranscript = useCallback((call: ActiveCall) => {
    // Disconnect previous
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setSelectedCall(call);
    setTranscriptMessages([]);

    console.log(`Connecting to live transcript for call: ${call.callSid}`);

    try {
      const es = createLiveTranscriptStream(call.callSid);
      eventSourceRef.current = es;

      es.onopen = () => {
        console.log('SSE connection opened');
      };

      // Listen to 'text' events from voice-server
      es.addEventListener('text', (event: MessageEvent) => {
        try {
          console.log('SSE text event received:', event.data);
          const data = JSON.parse(event.data);
          if (data.role && data.text) {
            setTranscriptMessages((prev) => [...prev, {
              role: data.role,
              content: data.text,
              timestamp: data.timestamp,
            }]);
          }
        } catch (err) {
          console.error('Failed to parse SSE text event:', err);
        }
      });

      // Listen to 'status' event (initial call info)
      es.addEventListener('status', (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          console.log('Call status received:', data);
        } catch (err) {
          console.error('Failed to parse SSE status event:', err);
        }
      });

      // Listen to 'done' event (call ended)
      es.addEventListener('done', (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          console.log('Call ended:', data.reason);
        } catch (err) {
          console.log('Call ended');
        }
        es.close();
        eventSourceRef.current = null;
      });

      es.onerror = (err) => {
        console.error('SSE connection error:', err);
        es.close();
        eventSourceRef.current = null;
      };
    } catch (err) {
      console.error('Failed to create SSE connection:', err);
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const activeCallColumns: ColumnsType<ActiveCall> = [
    {
      title: 'Customer',
      key: 'customer',
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.customerName || 'Unknown'}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <PhoneOutlined /> {record.customerPhone}
          </Text>
        </Space>
      ),
    },
    {
      title: 'Voice',
      dataIndex: 'voiceId',
      key: 'voiceId',
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: 'Duration',
      key: 'duration',
      render: (_, record) => (
        <Text>
          <ClockCircleOutlined style={{ marginRight: 4 }} />
          {formatDuration(record.startTime)}
        </Text>
      ),
    },
    {
      title: 'Turns',
      dataIndex: 'turnCount',
      key: 'turnCount',
      width: 70,
      render: (v: number) => <Tag color="blue">{v}</Tag>,
    },
  ];

  const recordColumns: ColumnsType<DynamoCallRecord> = [
    {
      title: 'Call SID',
      dataIndex: 'callSid',
      key: 'callSid',
      render: (sid: string) => (
        <Text code style={{ fontSize: 11 }}>
          {sid.substring(0, 12)}...
        </Text>
      ),
    },
    {
      title: 'Customer',
      key: 'customer',
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text strong style={{ fontSize: 12 }}>{record.customerName || '-'}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{record.customerPhone || '-'}</Text>
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Tag color={status === 'active' ? 'green' : 'default'}>{status}</Tag>
      ),
    },
    {
      title: 'Start',
      dataIndex: 'startTime',
      key: 'startTime',
      render: (t: string) => t ? dayjs(t).format('MM-DD HH:mm') : '-',
    },
    {
      title: 'End Reason',
      dataIndex: 'endReason',
      key: 'endReason',
      render: (r: string) => r ? <Tag>{r}</Tag> : <Text type="secondary">-</Text>,
    },
    {
      title: 'Turns',
      dataIndex: 'turnCount',
      key: 'turnCount',
      width: 60,
      render: (v: number) => <Tag color="blue">{v ?? 0}</Tag>,
    },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Panel A — Active Calls */}
      <Card
        className="glass-card fade-in"
        title={
          <Space>
            {activeCalls.length > 0 ? (
              <Badge status="success" />
            ) : (
              <Badge status="default" />
            )}
            <span>Active Calls</span>
            {activeCalls.length > 0 && (
              <Tag color="green">{activeCalls.length}</Tag>
            )}
          </Space>
        }
        size="small"
      >
        {activeCalls.length > 0 ? (
          <Table
            columns={activeCallColumns}
            dataSource={activeCalls}
            rowKey="callSid"
            pagination={false}
            size="small"
            onRow={(record) => ({
              onClick: () => connectTranscript(record),
              style: {
                cursor: 'pointer',
                background: selectedCall?.callSid === record.callSid ? '#e6f7ff' : undefined,
              },
            })}
          />
        ) : (
          <Empty description="No active calls" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      {/* Bottom row: Call History + Live Transcript */}
      <div style={{ display: 'flex', gap: 16 }}>
        {/* Panel B — Call History */}
        <Card
          className="glass-card fade-in"
          title="Call History"
          size="small"
          style={{ flex: 1 }}
        >
          {callRecords.length > 0 ? (
            <Table
              columns={recordColumns}
              dataSource={callRecords}
              rowKey="callSid"
              pagination={false}
              size="small"
              scroll={{ y: 400 }}
            />
          ) : (
            <Empty description="No call records" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          )}
        </Card>

        {/* Panel C — Live Transcript */}
        <Card
          className="glass-card fade-in"
          title={
            <Space>
              <MessageOutlined />
              <span>Live Transcript</span>
              {selectedCall && (
                <Tag color="blue">{selectedCall.customerName || selectedCall.customerPhone}</Tag>
              )}
            </Space>
          }
          size="small"
          style={{ flex: 1 }}
        >
          {selectedCall ? (
            <div
              style={{
                height: 400,
                overflowY: 'auto',
                padding: 8,
                backgroundColor: '#f5f5f5',
                borderRadius: 6,
              }}
            >
              {transcriptMessages.length === 0 ? (
                <div style={{ textAlign: 'center', paddingTop: 40 }}>
                  <Text type="secondary">Waiting for transcript data...</Text>
                </div>
              ) : (
                transcriptMessages.map((msg, idx) => {
                  const isUser = msg.role === 'user' || msg.role === 'CUSTOMER';
                  return (
                    <div
                      key={idx}
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: isUser ? 'flex-end' : 'flex-start',
                        marginBottom: 10,
                      }}
                    >
                      <Text type="secondary" style={{ fontSize: 11, marginBottom: 2 }}>
                        {isUser ? 'Customer' : 'Assistant'}
                      </Text>
                      <div
                        style={{
                          maxWidth: '80%',
                          padding: '8px 12px',
                          borderRadius: isUser ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                          backgroundColor: isUser ? '#1668dc' : '#e6f7ff',
                          color: isUser ? '#fff' : 'rgba(0,0,0,0.85)',
                        }}
                      >
                        <Text style={{ color: isUser ? '#fff' : 'rgba(0,0,0,0.85)' }}>{msg.content}</Text>
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={transcriptEndRef} />
            </div>
          ) : (
            <div style={{ height: 400, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Empty description="Select an active call to view live transcript" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
