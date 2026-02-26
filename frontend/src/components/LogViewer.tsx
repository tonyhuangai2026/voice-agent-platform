import React, { useState, useEffect } from 'react';
import { Modal, Table, Tag, Typography, Spin, Alert, Empty } from 'antd';
import { getCallLogs } from '../api';
import type { ColumnType } from 'antd/es/table';

const { Text } = Typography;

interface CallLog {
  callSid: string;
  timestamp: string;
  level: 'info' | 'warn' | 'error' | 'debug';
  event: string;
  message: string;
  metadata?: Record<string, any>;
}

interface LogViewerProps {
  callSid: string;
  visible: boolean;
  onClose: () => void;
}

const LogViewer: React.FC<LogViewerProps> = ({ callSid, visible, onClose }) => {
  const [logs, setLogs] = useState<CallLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (visible && callSid) {
      fetchLogs();
    }
  }, [visible, callSid]);

  const fetchLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getCallLogs(callSid);
      setLogs(data.logs || []);
    } catch (err: any) {
      console.error('Failed to fetch logs:', err);
      setError(err.response?.data?.error || err.message || 'Failed to load logs');
    } finally {
      setLoading(false);
    }
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'info': return 'blue';
      case 'warn': return 'orange';
      case 'error': return 'red';
      case 'debug': return 'default';
      default: return 'default';
    }
  };

  const columns: ColumnType<CallLog>[] = [
    {
      title: 'Time',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 180,
      render: (timestamp: string) => {
        const date = new Date(timestamp);
        return (
          <Text style={{ fontSize: 12, fontFamily: 'monospace' }}>
            {date.toLocaleString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
              second: '2-digit',
              fractionalSecondDigits: 3,
            })}
          </Text>
        );
      },
    },
    {
      title: 'Level',
      dataIndex: 'level',
      key: 'level',
      width: 80,
      render: (level: string) => (
        <Tag color={getLevelColor(level)} style={{ fontFamily: 'monospace', fontSize: 11 }}>
          {level.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Event',
      dataIndex: 'event',
      key: 'event',
      width: 150,
      render: (event: string) => (
        <Text style={{ fontFamily: 'monospace', fontSize: 12 }} strong>
          {event}
        </Text>
      ),
    },
    {
      title: 'Message',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
      render: (message: string) => (
        <Text style={{ fontSize: 12 }}>{message}</Text>
      ),
    },
    {
      title: 'Metadata',
      dataIndex: 'metadata',
      key: 'metadata',
      width: 100,
      render: (metadata?: Record<string, any>) => {
        if (!metadata || Object.keys(metadata).length === 0) return <Text type="secondary">-</Text>;
        return (
          <Text
            type="secondary"
            style={{ fontSize: 11, cursor: 'pointer' }}
            onClick={() => {
              Modal.info({
                title: 'Metadata',
                content: <pre style={{ fontSize: 12 }}>{JSON.stringify(metadata, null, 2)}</pre>,
                width: 600,
              });
            }}
          >
            View ({Object.keys(metadata).length})
          </Text>
        );
      },
    },
  ];

  return (
    <Modal
      title={`Call Logs - ${callSid}`}
      open={visible}
      onCancel={onClose}
      width={1200}
      footer={null}
      bodyStyle={{ padding: '16px' }}
    >
      {error && (
        <Alert
          type="error"
          message="Error loading logs"
          description={error}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin size="large" />
        </div>
      ) : logs.length === 0 ? (
        <Empty description="No logs found for this call" />
      ) : (
        <Table
          columns={columns}
          dataSource={logs}
          rowKey={(record) => `${record.timestamp}-${record.event}`}
          pagination={false}
          size="small"
          scroll={{ y: 500 }}
        />
      )}
    </Modal>
  );
};

export default LogViewer;
