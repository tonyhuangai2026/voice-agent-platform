import { useState, useEffect } from 'react';
import { Card, Table, Button, Space, Typography, Tag, message, Modal, Form, Input, Switch, Popconfirm } from 'antd';
import { ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined, ApiOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { listFlows, createFlow, updateFlow, deleteFlow } from '../api';
import type { FlowConfig } from '../types';
import { useProject } from '../contexts/ProjectContext';

const { Title, Text } = Typography;
const { TextArea } = Input;

export function FlowManagement() {
  const { currentProject } = useProject();
  const [flows, setFlows] = useState<FlowConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingFlow, setEditingFlow] = useState<FlowConfig | null>(null);
  const [form] = Form.useForm();

  const fetchFlows = async () => {
    setLoading(true);
    try {
      const data = await listFlows(undefined, currentProject?.project_id);
      setFlows(data.flows);
    } catch (error) {
      console.error('Failed to fetch flows:', error);
      message.error('Failed to load flows');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFlows();
  }, [currentProject]);

  const handleCreate = () => {
    setEditingFlow(null);
    form.resetFields();
    setModalVisible(true);
  };

  const handleEdit = (flow: FlowConfig) => {
    setEditingFlow(flow);
    form.setFieldsValue({
      flow_name: flow.flow_name,
      instance_id: flow.instance_id,
      contact_flow_id: flow.contact_flow_id,
      queue_id: flow.queue_id,
      description: flow.description,
      is_active: flow.is_active
    });
    setModalVisible(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      if (editingFlow) {
        // Update existing flow
        await updateFlow(editingFlow.flow_id, values);
        message.success('Flow updated');
      } else {
        // Create new flow with current project_id
        await createFlow({
          ...values,
          project_id: currentProject?.project_id || ''
        });
        message.success('Flow created');
      }

      setModalVisible(false);
      fetchFlows();
    } catch (error) {
      message.error('Failed to save flow');
    }
  };

  const handleDelete = async (flowId: string) => {
    try {
      await deleteFlow(flowId);
      message.success('Flow deleted');
      fetchFlows();
    } catch (error) {
      message.error('Failed to delete flow');
    }
  };

  const columns: ColumnsType<FlowConfig> = [
    {
      title: 'Flow Name',
      dataIndex: 'flow_name',
      key: 'flow_name',
      render: (name: string) => (
        <Space>
          <ApiOutlined />
          <Text strong>{name}</Text>
        </Space>
      ),
    },
    {
      title: 'Instance ID',
      dataIndex: 'instance_id',
      key: 'instance_id',
      render: (id: string) => (
        <Text code style={{ fontSize: '11px' }}>{id.substring(0, 20)}...</Text>
      ),
    },
    {
      title: 'Contact Flow ID',
      dataIndex: 'contact_flow_id',
      key: 'contact_flow_id',
      render: (id: string) => (
        <Text code style={{ fontSize: '11px' }}>{id.substring(0, 20)}...</Text>
      ),
    },
    {
      title: 'Queue ID',
      dataIndex: 'queue_id',
      key: 'queue_id',
      render: (id: string) => (
        <Text code style={{ fontSize: '11px' }}>{id.substring(0, 20)}...</Text>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active: boolean) => (
        <Tag color={active ? 'success' : 'default'}>
          {active ? 'Active' : 'Inactive'}
        </Tag>
      ),
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (time: string) => dayjs(time).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete this flow?"
            description="This action cannot be undone"
            onConfirm={() => handleDelete(record.flow_id)}
            okText="Yes"
            cancelText="No"
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card>
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            <ApiOutlined style={{ marginRight: 8 }} />
            Flow Configuration
          </Title>
          <Space>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleCreate}
            >
              Add Flow
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchFlows}
              loading={loading}
            >
              Refresh
            </Button>
          </Space>
        </div>

        <Table
          columns={columns}
          dataSource={flows}
          rowKey="flow_id"
          loading={loading}
          pagination={false}
          size="small"
        />
      </Space>

      {/* Create/Edit Modal */}
      <Modal
        title={editingFlow ? 'Edit Flow' : 'Create Flow'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={700}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="flow_name"
            label="Flow Name"
            rules={[{ required: true, message: 'Please enter flow name' }]}
          >
            <Input placeholder="e.g., Default Outbound Flow" />
          </Form.Item>

          <Form.Item
            name="instance_id"
            label="Amazon Connect Instance ID"
            rules={[{ required: true, message: 'Please enter instance ID' }]}
          >
            <Input placeholder="e.g., a60dd182-7f8f-495b-945e-43420832f01c" />
          </Form.Item>

          <Form.Item
            name="contact_flow_id"
            label="Contact Flow ID"
            rules={[{ required: true, message: 'Please enter contact flow ID' }]}
          >
            <Input placeholder="e.g., ccd673d3-3d38-4235-9818-e1b65c1d7225" />
          </Form.Item>

          <Form.Item
            name="queue_id"
            label="Queue ID"
            rules={[{ required: true, message: 'Please enter queue ID' }]}
          >
            <Input placeholder="e.g., 1eced15c-4c63-42d7-8faf-13c4cf28455a" />
          </Form.Item>

          <Form.Item name="description" label="Description">
            <TextArea rows={3} placeholder="Optional description for this flow" />
          </Form.Item>

          <Form.Item name="is_active" label="Active" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
