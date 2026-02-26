import { useState, useEffect } from 'react';
import { Card, Table, Button, Modal, Form, Input, Select, Switch, Space, message, Tag, Popconfirm, Typography } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, TagsOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { listLabels, createLabel, updateLabel, deleteLabel } from '../api';
import type { LabelConfig } from '../types';
import { useProject } from '../contexts/ProjectContext';

const { Title, Text } = Typography;

export function LabelManagement() {
  const { currentProject } = useProject();
  const [labels, setLabels] = useState<LabelConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingLabel, setEditingLabel] = useState<LabelConfig | null>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    if (currentProject) {
      fetchLabels();
    }
  }, [currentProject]);

  const fetchLabels = async () => {
    if (!currentProject) return;
    setLoading(true);
    try {
      const data = await listLabels(currentProject.project_id);
      setLabels(data.labels);
    } catch (error) {
      message.error('Failed to load labels');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingLabel(null);
    form.resetFields();
    form.setFieldsValue({
      is_active: true,
      label_type: 'single',
    });
    setModalVisible(true);
  };

  const handleEdit = (label: LabelConfig) => {
    setEditingLabel(label);
    form.setFieldsValue(label);
    setModalVisible(true);
  };

  const handleDelete = async (labelId: string) => {
    try {
      await deleteLabel(labelId);
      message.success('Label deleted successfully');
      fetchLabels();
    } catch (error) {
      message.error('Failed to delete label');
      console.error(error);
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();

      if (!currentProject) {
        message.error('No project selected');
        return;
      }

      if (editingLabel) {
        // Update existing label
        await updateLabel(editingLabel.label_id, values);
        message.success('Label updated successfully');
      } else {
        // Create new label
        await createLabel({
          ...values,
          project_id: currentProject.project_id,
        });
        message.success('Label created successfully');
      }

      setModalVisible(false);
      fetchLabels();
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  };

  const columns: ColumnsType<LabelConfig> = [
    {
      title: 'Label Name',
      dataIndex: 'label_name',
      key: 'label_name',
      render: (name: string) => (
        <Space>
          <TagsOutlined style={{ color: '#667eea' }} />
          <Text strong>{name}</Text>
        </Space>
      ),
    },
    {
      title: 'Type',
      dataIndex: 'label_type',
      key: 'label_type',
      width: 120,
      render: (type: string) => (
        <Tag color={type === 'single' ? 'blue' : 'purple'}>
          {type === 'single' ? 'Single Select' : 'Multiple Select'}
        </Tag>
      ),
    },
    {
      title: 'Options',
      dataIndex: 'options',
      key: 'options',
      render: (options: string[]) => (
        <Space wrap>
          {options.slice(0, 3).map((opt, idx) => (
            <Tag key={idx}>{opt}</Tag>
          ))}
          {options.length > 3 && <Text type="secondary">+{options.length - 3} more</Text>}
        </Space>
      ),
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
      render: (desc: string) => <Text type="secondary">{desc || '-'}</Text>,
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      key: 'is_active',
      width: 100,
      render: (active: boolean) => (
        <Tag color={active ? 'green' : 'default'}>{active ? 'Active' : 'Inactive'}</Tag>
      ),
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 120,
      render: (time: string) => dayjs(time).format('MM-DD HH:mm'),
    },
    {
      title: 'Action',
      key: 'action',
      width: 150,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            Edit
          </Button>
          <Popconfirm
            title="Delete label"
            description="Are you sure you want to delete this label?"
            onConfirm={() => handleDelete(record.label_id)}
            okText="Yes"
            cancelText="No"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  if (!currentProject) {
    return (
      <Card>
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Text type="secondary">Please select a project to manage labels</Text>
        </div>
      </Card>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card className="glass-card fade-in" size="small">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            <TagsOutlined style={{ marginRight: 8 }} />
            Call Labels Configuration
          </Title>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            Create Label
          </Button>
        </div>
      </Card>

      <Card className="glass-card fade-in" size="small">
        <Table
          columns={columns}
          dataSource={labels}
          rowKey="label_id"
          loading={loading}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (total) => `Total ${total} labels`,
          }}
        />
      </Card>

      <Modal
        title={editingLabel ? 'Edit Label' : 'Create Label'}
        open={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={handleSubmit}
        width={600}
        okText={editingLabel ? 'Update' : 'Create'}
      >
        <Form
          form={form}
          layout="vertical"
          style={{ marginTop: 20 }}
        >
          <Form.Item
            name="label_name"
            label="Label Name"
            rules={[{ required: true, message: 'Please enter label name' }]}
          >
            <Input placeholder="e.g., Call Result, Customer Sentiment" />
          </Form.Item>

          <Form.Item
            name="label_type"
            label="Selection Type"
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="single">Single Select (Radio)</Select.Option>
              <Select.Option value="multiple">Multiple Select (Checkbox)</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            name="options"
            label="Options"
            rules={[
              { required: true, message: 'Please enter at least one option' },
              {
                validator: (_, value) => {
                  if (value && value.length > 0) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('At least one option is required'));
                },
              },
            ]}
          >
            <Select
              mode="tags"
              placeholder="Type and press Enter to add options"
              style={{ width: '100%' }}
            />
          </Form.Item>

          <Form.Item
            name="description"
            label="Description (Optional)"
          >
            <Input.TextArea
              rows={3}
              placeholder="Describe what this label is used for"
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
    </div>
  );
}
