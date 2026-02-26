import { useState, useEffect } from 'react';
import { Card, Table, Button, Space, Typography, Tag, message, Modal, Form, Input, Switch, Popconfirm } from 'antd';
import { ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined, FileTextOutlined, EyeOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { listPrompts, createPrompt, updatePrompt, deletePrompt } from '../api';
import type { PromptConfig } from '../types';

const { Title, Text } = Typography;
const { TextArea } = Input;

export function PromptManagement() {
  const [prompts, setPrompts] = useState<PromptConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [viewModalVisible, setViewModalVisible] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState<PromptConfig | null>(null);
  const [viewingPrompt, setViewingPrompt] = useState<PromptConfig | null>(null);
  const [form] = Form.useForm();

  const fetchPrompts = async () => {
    setLoading(true);
    try {
      // Don't filter by project for prompts - show all including system defaults
      const data = await listPrompts();
      setPrompts(data.prompts);
    } catch (error) {
      console.error('Failed to fetch prompts:', error);
      message.error('Failed to load prompts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPrompts();
  }, []);

  const handleCreate = () => {
    setEditingPrompt(null);
    form.resetFields();
    form.setFieldsValue({ is_active: true });
    setModalVisible(true);
  };

  const handleEdit = (prompt: PromptConfig) => {
    setEditingPrompt(prompt);
    form.setFieldsValue({
      prompt_name: prompt.prompt_name,
      prompt_content: prompt.prompt_content,
      description: prompt.description,
      is_active: prompt.is_active
    });
    setModalVisible(true);
  };

  const handleView = (prompt: PromptConfig) => {
    setViewingPrompt(prompt);
    setViewModalVisible(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      if (editingPrompt) {
        // Update existing prompt
        await updatePrompt(editingPrompt.prompt_id, values);
        message.success('Prompt updated');
      } else {
        // Create new prompt
        await createPrompt(values);
        message.success('Prompt created');
      }

      setModalVisible(false);
      fetchPrompts();
    } catch (error) {
      message.error('Failed to save prompt');
    }
  };

  const handleDelete = async (promptId: string) => {
    try {
      await deletePrompt(promptId);
      message.success('Prompt deleted');
      fetchPrompts();
    } catch (error) {
      message.error('Failed to delete prompt');
    }
  };

  const columns: ColumnsType<PromptConfig> = [
    {
      title: 'Prompt Name',
      dataIndex: 'prompt_name',
      key: 'prompt_name',
      render: (name: string) => (
        <Space>
          <FileTextOutlined />
          <Text strong>{name}</Text>
        </Space>
      ),
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
      render: (desc: string) => (
        <Text type="secondary">{desc || '-'}</Text>
      ),
    },
    {
      title: 'Content Preview',
      dataIndex: 'prompt_content',
      key: 'preview',
      render: (content: string) => (
        <Text ellipsis style={{ maxWidth: 300 }}>
          {content.substring(0, 80)}...
        </Text>
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
            icon={<EyeOutlined />}
            onClick={() => handleView(record)}
          >
            View
          </Button>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete this prompt?"
            description="This action cannot be undone."
            onConfirm={() => handleDelete(record.prompt_id)}
            okText="Delete"
            cancelText="Cancel"
            okButtonProps={{ danger: true }}
          >
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Title level={3} style={{ margin: 0 }}>Prompt Templates</Title>
            <Space>
              <Button
                icon={<ReloadOutlined />}
                onClick={fetchPrompts}
                loading={loading}
              >
                Refresh
              </Button>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={handleCreate}
              >
                Create Prompt
              </Button>
            </Space>
          </div>

          <Table
            columns={columns}
            dataSource={prompts}
            rowKey="prompt_id"
            loading={loading}
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `Total ${total} prompts`,
            }}
          />
        </Space>
      </Card>

      {/* Create/Edit Modal */}
      <Modal
        title={editingPrompt ? 'Edit Prompt' : 'Create Prompt'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={800}
        okText="Save"
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="prompt_name"
            label="Prompt Name"
            rules={[{ required: true, message: 'Please enter prompt name' }]}
          >
            <Input placeholder="e.g., Default Outbound Collection" />
          </Form.Item>
          <Form.Item
            name="description"
            label="Description"
          >
            <Input placeholder="Brief description of this prompt template" />
          </Form.Item>
          <Form.Item
            name="prompt_content"
            label="Prompt Content"
            rules={[{ required: true, message: 'Please enter prompt content' }]}
          >
            <TextArea
              rows={15}
              placeholder="Enter the system prompt content..."
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Form.Item
            name="is_active"
            label="Active"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* View Modal */}
      <Modal
        title={`View Prompt: ${viewingPrompt?.prompt_name || ''}`}
        open={viewModalVisible}
        onCancel={() => setViewModalVisible(false)}
        width={900}
        footer={[
          <Button key="copy" onClick={() => {
            if (viewingPrompt) {
              navigator.clipboard.writeText(viewingPrompt.prompt_content);
              message.success('Prompt content copied to clipboard');
            }
          }}>
            Copy to Clipboard
          </Button>,
          <Button key="close" type="primary" onClick={() => setViewModalVisible(false)}>
            Close
          </Button>
        ]}
      >
        {viewingPrompt && (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text strong>Description:</Text>
              <div style={{ marginTop: 8 }}>
                <Text type="secondary">{viewingPrompt.description || 'No description'}</Text>
              </div>
            </div>
            <div>
              <Text strong>Status:</Text>
              <div style={{ marginTop: 8 }}>
                <Tag color={viewingPrompt.is_active ? 'success' : 'default'}>
                  {viewingPrompt.is_active ? 'Active' : 'Inactive'}
                </Tag>
              </div>
            </div>
            <div>
              <Text strong>Prompt Content:</Text>
              <div style={{
                marginTop: 8,
                padding: 16,
                backgroundColor: '#141414',
                borderRadius: 4,
                maxHeight: 500,
                overflow: 'auto'
              }}>
                <pre style={{
                  margin: 0,
                  fontFamily: 'monospace',
                  fontSize: '12px',
                  whiteSpace: 'pre-wrap',
                  wordWrap: 'break-word'
                }}>
                  {viewingPrompt.prompt_content}
                </pre>
              </div>
            </div>
            <div>
              <Text type="secondary" style={{ fontSize: '12px' }}>
                Created: {dayjs(viewingPrompt.created_at).format('YYYY-MM-DD HH:mm')} |
                Updated: {dayjs(viewingPrompt.updated_at).format('YYYY-MM-DD HH:mm')}
              </Text>
            </div>
          </Space>
        )}
      </Modal>
    </div>
  );
}
