import { useState, useEffect } from 'react';
import { Card, Typography, Spin, Empty, Button, Tag, Space, Descriptions, message, Divider } from 'antd';
import { CloseOutlined, UserOutlined, RobotOutlined, PhoneOutlined, ExperimentOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { getTranscript, analyzeConversation, getAnalysis } from '../api';
import type { TranscriptDetail, ChatMessage, AnalysisResult } from '../types';

const { Title, Text } = Typography;

interface ChatViewerProps {
  contactId: string | null;
  onClose: () => void;
}

export function ChatViewer({ contactId, onClose }: ChatViewerProps) {
  const [transcript, setTranscript] = useState<TranscriptDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    if (contactId) {
      setLoading(true);
      setAnalysis(null);

      // Load transcript and existing analysis
      Promise.all([
        getTranscript(contactId),
        getAnalysis(contactId)
      ])
        .then(([transcriptData, analysisData]) => {
          setTranscript(transcriptData);
          if (analysisData.exists && analysisData.analysis) {
            setAnalysis(analysisData.analysis);
          }
        })
        .catch((error) => {
          console.error('Failed to load data:', error);
          setTranscript(null);
        })
        .finally(() => setLoading(false));
    } else {
      setTranscript(null);
      setAnalysis(null);
    }
  }, [contactId]);

  const handleAnalyze = async () => {
    if (!contactId) return;

    setAnalyzing(true);
    try {
      const result = await analyzeConversation(contactId);
      setAnalysis(result.analysis);
      message.success('Analysis completed');
    } catch (error) {
      console.error('Analysis failed:', error);
      message.error('Analysis failed. Please try again.');
    } finally {
      setAnalyzing(false);
    }
  };

  if (!contactId) {
    return (
      <Card>
        <Empty description="Select a contact to view details" />
      </Card>
    );
  }

  if (loading) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <Spin size="large" />
          <Text style={{ display: 'block', marginTop: 16 }}>Loading...</Text>
        </div>
      </Card>
    );
  }

  if (!transcript) {
    return (
      <Card>
        <Empty description="Failed to load contact details" />
      </Card>
    );
  }

  return (
    <Card
      title={
        <Space>
          <Title level={5} style={{ margin: 0 }}>Contact Details</Title>
          <Tag color="purple">{contactId.substring(0, 8)}...</Tag>
        </Space>
      }
      extra={
        <Button icon={<CloseOutlined />} onClick={onClose} type="text">
          Close
        </Button>
      }
    >
      {/* Contact Info Section */}
      <Descriptions
        bordered
        size="small"
        column={2}
        style={{ marginBottom: 16 }}
      >
        {transcript.customerName && (
          <Descriptions.Item label="Customer Name">
            <Text strong>{transcript.customerName}</Text>
          </Descriptions.Item>
        )}
        {transcript.customerPhone && (
          <Descriptions.Item label="Customer Phone">
            <Space>
              <PhoneOutlined />
              <Text code>{transcript.customerPhone}</Text>
            </Space>
          </Descriptions.Item>
        )}
        {transcript.systemPhone && (
          <Descriptions.Item label="System Phone">
            <Text code>{transcript.systemPhone}</Text>
          </Descriptions.Item>
        )}
        {transcript.debtAmount && (
          <Descriptions.Item label="Debt Amount">
            <Tag color="red">${transcript.debtAmount}</Tag>
          </Descriptions.Item>
        )}
        {transcript.channel && (
          <Descriptions.Item label="Channel">
            <Tag color="blue">{transcript.channel}</Tag>
          </Descriptions.Item>
        )}
        {transcript.initiationMethod && (
          <Descriptions.Item label="Method">
            <Tag>{transcript.initiationMethod}</Tag>
          </Descriptions.Item>
        )}
        {transcript.disconnectReason && (
          <Descriptions.Item label="Result" span={2}>
            <Tag color={transcript.disconnectReason === 'CUSTOMER_DISCONNECT' ? 'green' : 'orange'}>
              {transcript.disconnectReason}
            </Tag>
          </Descriptions.Item>
        )}
      </Descriptions>

      {/* Analysis Section */}
      <Divider>
        <Space>
          <ExperimentOutlined />
          <span>AI Analysis</span>
        </Space>
      </Divider>

      {analysis ? (
        <div style={{ marginBottom: 16 }}>
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="Outcome Tag">
              <Tag color="blue" style={{ fontSize: '14px', padding: '4px 12px' }}>
                {analysis.outcomeTag.code}: {analysis.outcomeTag.label}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Behavior Tags">
              {analysis.behaviorTags.length > 0 ? (
                <Space wrap>
                  {analysis.behaviorTags.map((tag) => (
                    <Tag key={tag.code} color="green">
                      {tag.label}
                    </Tag>
                  ))}
                </Space>
              ) : (
                <Text type="secondary">None</Text>
              )}
            </Descriptions.Item>
            {analysis.analyzedAt && (
              <Descriptions.Item label="Analyzed At">
                <Text type="secondary">
                  {dayjs(analysis.analyzedAt).format('YYYY-MM-DD HH:mm:ss')}
                </Text>
              </Descriptions.Item>
            )}
          </Descriptions>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '16px' }}>
          <Button
            type="primary"
            icon={analyzing ? undefined : <ExperimentOutlined />}
            onClick={handleAnalyze}
            loading={analyzing}
            disabled={!transcript.messages || transcript.messages.length === 0}
          >
            {analyzing ? 'Analyzing...' : 'Analyze Conversation'}
          </Button>
          {(!transcript.messages || transcript.messages.length === 0) && (
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
              No transcript available for analysis
            </Text>
          )}
        </div>
      )}

      {analysis && (
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <Button
            icon={<ExperimentOutlined />}
            onClick={handleAnalyze}
            loading={analyzing}
            size="small"
          >
            Re-analyze
          </Button>
        </div>
      )}

      {/* Chat Messages Section */}
      {transcript.messages && transcript.messages.length > 0 ? (
        <>
          <Title level={5} style={{ marginBottom: 12 }}>Chat History</Title>
          <div
            style={{
              maxHeight: '400px',
              overflowY: 'auto',
              padding: '8px',
              backgroundColor: '#f5f5f5',
              borderRadius: '8px',
            }}
          >
            {transcript.messages.map((msg) => (
              <ChatBubble key={msg.id} message={msg} />
            ))}
          </div>
        </>
      ) : (
        <Empty description="No chat messages available" style={{ marginTop: 20 }} />
      )}
    </Card>
  );
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isCustomer = message.role === 'CUSTOMER';
  const isBot = message.displayName === 'BOT' || message.displayName === 'SYSTEM_MESSAGE' || message.displayName === 'Bot';

  // Clean up SSML content
  let content = message.content;
  if (content.includes('<speak>')) {
    content = content.replace(/<[^>]*>/g, '').trim();
  }

  const bubbleStyle: React.CSSProperties = {
    maxWidth: '70%',
    padding: '10px 14px',
    borderRadius: isCustomer ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
    backgroundColor: isCustomer ? '#1890ff' : '#fff',
    color: isCustomer ? '#fff' : '#333',
    marginLeft: isCustomer ? 'auto' : '0',
    marginRight: isCustomer ? '0' : 'auto',
    boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
  };

  const containerStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: isCustomer ? 'flex-end' : 'flex-start',
    marginBottom: '12px',
  };

  // Format time - use timestamp if available, otherwise format offsetMs
  const formatTime = () => {
    if (message.timestamp) {
      return dayjs(message.timestamp).format('HH:mm:ss');
    }
    if (message.offsetMs !== undefined) {
      const seconds = Math.floor(message.offsetMs / 1000);
      const mins = Math.floor(seconds / 60);
      const secs = seconds % 60;
      return `${mins}:${secs.toString().padStart(2, '0')}`;
    }
    return '';
  };

  return (
    <div style={containerStyle}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 4 }}>
        {!isCustomer && (
          <RobotOutlined style={{ marginRight: 4, color: '#666' }} />
        )}
        <Text type="secondary" style={{ fontSize: '12px' }}>
          {isCustomer ? 'Customer' : isBot ? 'Bot' : message.displayName}
        </Text>
        {isCustomer && (
          <UserOutlined style={{ marginLeft: 4, color: '#1890ff' }} />
        )}
        {message.sentiment && (
          <Tag color={message.sentiment === 'POSITIVE' ? 'green' : message.sentiment === 'NEGATIVE' ? 'red' : 'default'} style={{ marginLeft: 4, fontSize: '10px' }}>
            {message.sentiment}
          </Tag>
        )}
      </div>
      <div style={bubbleStyle}>
        <Text style={{ color: isCustomer ? '#fff' : '#333' }}>{content}</Text>
      </div>
      <Text type="secondary" style={{ fontSize: '10px', marginTop: 4 }}>
        {formatTime()}
      </Text>
    </div>
  );
}
