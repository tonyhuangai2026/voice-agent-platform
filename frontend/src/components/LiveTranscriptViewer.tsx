import { useEffect, useRef, useState } from 'react';
import { Drawer, Tag, Typography, Space, Divider, Empty } from 'antd';
import { createLiveTranscriptStream, getCallRecord } from '../api';
import type { DynamoCallRecord } from '../types';

const { Text, Title } = Typography;

interface TranscriptLine {
  role: 'user' | 'assistant';
  text: string;
  timestamp: string;
}

interface Props {
  callSid: string | null;
  customerName?: string;
  customerPhone?: string;
  onClose: () => void;
}

export function LiveTranscriptViewer({ callSid, customerName, customerPhone, onClose }: Props) {
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [connected, setConnected] = useState(false);
  const [ended, setEnded] = useState(false);
  const [startTime, setStartTime] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState('0:00');
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines]);

  // Elapsed time ticker
  useEffect(() => {
    if (!startTime || ended) return;
    const start = new Date(startTime).getTime();
    const interval = setInterval(() => {
      const diff = Math.floor((Date.now() - start) / 1000);
      const m = Math.floor(diff / 60);
      const s = diff % 60;
      setElapsed(`${m}:${s.toString().padStart(2, '0')}`);
    }, 1000);
    return () => clearInterval(interval);
  }, [startTime, ended]);

  // SSE or DynamoDB fetch
  useEffect(() => {
    if (!callSid) return;

    setLines([]);
    setConnected(false);
    setEnded(false);
    setStartTime(null);

    // Try SSE first for live calls
    const es = createLiveTranscriptStream(callSid);

    es.addEventListener('status', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setConnected(true);
      setStartTime(data.startTime);
    });

    es.addEventListener('text', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setLines((prev) => [...prev, { role: data.role, text: data.text, timestamp: data.timestamp }]);
    });

    es.addEventListener('done', (e: MessageEvent) => {
      const data = JSON.parse(e.data);
      setEnded(true);
      setConnected(false);
      es.close();
      // Reload full transcript from DynamoDB
      loadFromDynamo(callSid, data.reason);
    });

    es.onerror = () => {
      // If SSE fails (call already ended), load from DynamoDB
      es.close();
      loadFromDynamo(callSid);
    };

    return () => {
      es.close();
    };
  }, [callSid]);

  const loadFromDynamo = async (sid: string, _reason?: string) => {
    try {
      const record: DynamoCallRecord = await getCallRecord(sid);
      setStartTime(record.startTime);
      setEnded(true);
      setConnected(false);
      if (record.transcript && record.transcript.length > 0) {
        setLines(record.transcript);
      }
    } catch {
      // Record not found
    }
  };

  const formatTime = (ts: string) => {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString('en-US', { hour12: false });
    } catch {
      return '';
    }
  };

  return (
    <Drawer
      title={
        <Space>
          <Title level={5} style={{ margin: 0 }}>
            Live Transcript
          </Title>
          {customerName && <Text type="secondary">- {customerName}</Text>}
          {customerPhone && <Text type="secondary">({customerPhone})</Text>}
        </Space>
      }
      open={!!callSid}
      onClose={onClose}
      width={520}
      destroyOnClose
    >
      <Space style={{ marginBottom: 12 }}>
        {connected && !ended && <Tag color="green">Connected</Tag>}
        {ended && <Tag color="default">Ended</Tag>}
        {!connected && !ended && callSid && <Tag color="orange">Connecting...</Tag>}
        <Text type="secondary">Duration: {elapsed}</Text>
        <Text type="secondary">Turns: {lines.length}</Text>
      </Space>
      <Divider style={{ margin: '8px 0' }} />

      <div
        ref={scrollRef}
        style={{ height: 'calc(100vh - 220px)', overflowY: 'auto', padding: '0 4px' }}
      >
        {lines.length === 0 && <Empty description="No transcript data yet" />}
        {lines.map((line, i) => (
          <div
            key={i}
            style={{
              marginBottom: 8,
              padding: '6px 10px',
              borderRadius: 6,
              background: line.role === 'assistant' ? '#f0f5ff' : '#f6ffed',
              borderLeft: `3px solid ${line.role === 'assistant' ? '#1677ff' : '#52c41a'}`,
            }}
          >
            <div style={{ marginBottom: 2 }}>
              <Text strong style={{ fontSize: 12, color: line.role === 'assistant' ? '#1677ff' : '#52c41a' }}>
                {line.role === 'assistant' ? 'Agent' : 'Customer'}
              </Text>
              {line.timestamp && (
                <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                  {formatTime(line.timestamp)}
                </Text>
              )}
            </div>
            <Text>{line.text}</Text>
          </div>
        ))}
        {connected && !ended && (
          <div style={{ padding: '6px 10px', color: '#999' }}>
            Listening...
          </div>
        )}
      </div>
    </Drawer>
  );
}
