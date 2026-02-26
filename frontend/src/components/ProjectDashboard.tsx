import { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Typography, Space, Tag, Empty, Spin } from 'antd';
import {
  PhoneOutlined,
  UserOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useProject } from '../contexts/ProjectContext';
import { getProjectStats } from '../api';
import type { ProjectStats } from '../types';

const { Title, Text } = Typography;

export function ProjectDashboard() {
  const { currentProject } = useProject();
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (currentProject) {
      loadStats();
    }
  }, [currentProject]);

  const loadStats = async () => {
    if (!currentProject) return;

    setLoading(true);
    try {
      const data = await getProjectStats(currentProject.project_id);
      setStats(data);
    } catch (error) {
      console.error('Failed to load stats:', error);
    } finally {
      setLoading(false);
    }
  };

  if (!currentProject) {
    return (
      <Card className="glass-card">
        <Empty description="No project selected" />
      </Card>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <Space direction="vertical" size={0}>
          <Title level={2} style={{ margin: 0 }}>
            Project Overview
          </Title>
          <Space>
            <Text type="secondary">{currentProject.project_name}</Text>
            <Tag color="purple">{currentProject.project_type}</Tag>
          </Space>
        </Space>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin size="large" />
        </div>
      ) : (
        <>
          {/* Stats Cards */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} sm={12} lg={6}>
              <Card className="stats-card" bordered={false}>
                <Statistic
                  title="Total Customers"
                  value={stats?.total_customers || 0}
                  prefix={<UserOutlined style={{ color: '#a78bfa' }} />}
                  valueStyle={{ color: '#a78bfa' }}
                />
              </Card>
            </Col>

            <Col xs={24} sm={12} lg={6}>
              <Card className="stats-card" bordered={false}>
                <Statistic
                  title="Total Calls"
                  value={stats?.total_calls || 0}
                  prefix={<PhoneOutlined style={{ color: '#4facfe' }} />}
                  valueStyle={{ color: '#4facfe' }}
                />
              </Card>
            </Col>

            <Col xs={24} sm={12} lg={6}>
              <Card className="stats-card" bordered={false}>
                <Statistic
                  title="Active Calls"
                  value={stats?.active_calls || 0}
                  prefix={<ClockCircleOutlined style={{ color: '#fbbf24' }} />}
                  valueStyle={{ color: '#fbbf24' }}
                />
              </Card>
            </Col>

            <Col xs={24} sm={12} lg={6}>
              <Card className="stats-card" bordered={false}>
                <Statistic
                  title="Success Rate"
                  value={stats?.success_rate || 0}
                  precision={1}
                  suffix="%"
                  prefix={<CheckCircleOutlined style={{ color: '#10b981' }} />}
                  valueStyle={{ color: '#10b981' }}
                />
              </Card>
            </Col>
          </Row>

          {/* Project Details */}
          <Card className="glass-card" title="Project Information">
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <Space direction="vertical" size={0}>
                  <Text type="secondary">Description</Text>
                  <Text>{currentProject.description || 'No description provided'}</Text>
                </Space>
              </Col>

              <Col span={6}>
                <Space direction="vertical" size={0}>
                  <Text type="secondary">Status</Text>
                  <Tag color={currentProject.status === 'active' ? 'green' : 'default'}>
                    {currentProject.status}
                  </Tag>
                </Space>
              </Col>

              <Col span={6}>
                <Space direction="vertical" size={0}>
                  <Text type="secondary">Created</Text>
                  <Text>{new Date(currentProject.created_at).toLocaleDateString()}</Text>
                </Space>
              </Col>

              {currentProject.settings?.voice_id && (
                <Col span={6}>
                  <Space direction="vertical" size={0}>
                    <Text type="secondary">Voice</Text>
                    <Text>{currentProject.settings.voice_id}</Text>
                  </Space>
                </Col>
              )}

              {currentProject.settings?.language && (
                <Col span={6}>
                  <Space direction="vertical" size={0}>
                    <Text type="secondary">Language</Text>
                    <Text>{currentProject.settings.language}</Text>
                  </Space>
                </Col>
              )}
            </Row>
          </Card>

          {/* Quick Actions */}
          <Card
            className="glass-card"
            title="Quick Actions"
            style={{ marginTop: 16 }}
          >
            <Space>
              <Text type="secondary">Navigate to:</Text>
              <a href="#customers">Customers</a>
              <a href="#prompts">Prompts</a>
              <a href="#flows">Flows</a>
              <a href="#monitor">Live Monitor</a>
            </Space>
          </Card>
        </>
      )}
    </div>
  );
}
